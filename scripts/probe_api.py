"""Mặc định chỉ audit offline. --execute cần checkpoint và phê duyệt riêng của bạn."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.api_probe import PLAN, ApiProbeClient, audit, probe_lock, project_response, schema_shape, search_url
from src.config import ROOT
from src.crawler import CrawlStopped

OUT = ROOT / 'analyses/2026-11-09_api_probe_preparation'


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def prepare():
    state, manifest, ids, urls = audit(ROOT)
    hashes = []
    # Chỉ kiểm hash tài liệu và bốn trang mới, không nhận là tái lập toàn bộ HTML.
    for meta in manifest:
        if meta['url'] in ('https://moso.vn/robots.txt', 'https://moso.vn/api/openapi.json',
                           'https://moso.vn/.well-known/webmcp/tools.json') or (
                meta['kind'] == 'list' and meta['thoi_diem_crawl'].startswith('2026-11-09')):
            path = ROOT / meta['html_path']
            matched = hashlib.sha256(path.read_bytes()).hexdigest() == meta['sha256']
            if not matched:
                raise CrawlStopped('Hash tài liệu hoặc trang probe không khớp.')
            hashes.append(dict(path=meta['html_path'], matched=matched))
    probe = json.loads((ROOT / 'analyses/2026-11-09_pagination_probe/result.json').read_text(encoding='utf-8'))
    pending = sorted({identifier for page in probe['pages'] for identifier in page['new_vs_baseline']} - ids)
    csv_path = ROOT / 'revisions/full_continued_1508/data/listings.csv'
    with csv_path.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames
        rows = list(reader)
    OUT.mkdir(exist_ok=True)
    result = dict(measurement='measured', state_count=state['request_count'], full_limit=state['limit'],
                  remaining=state['limit'] - state['request_count'], manifest_rows=len(manifest),
                  saved_detail_ids=len(ids), saved_detail_urls=len(urls), pending_ids=pending,
                  selected_hash_checks=hashes, full_html_integrity='not_reverified',
                  csv_rows=len(rows), csv_columns=len(columns), csv_unique_ids=len({r['tin_id'] for r in rows}),
                  csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                  new_http_attempts=0, proposed_max_attempts=20,
                  proposed_requests=[search_url(*item) for item in PLAN],
                  schema_adapter='unverified_until_live_response', detail_downloads_allowed=False)
    write_json(OUT / 'offline_audit.json', result)
    print(json.dumps({key: result[key] for key in ('state_count', 'saved_detail_ids', 'new_http_attempts')}))


def execute(checkpoint, max_attempts=20):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 20:
        raise CrawlStopped('Trần phép thử phải từ 1 đến 20.')
    output = ROOT / f'analyses/api_probe_from_{checkpoint}'
    with probe_lock(ROOT):
        state, _, _, _ = audit(ROOT)
        if state['request_count'] != checkpoint:
            raise CrawlStopped('Checkpoint khác gói thử được duyệt.')
        output.mkdir(exist_ok=False)
        write_json(output / 'state_before.json', state)
        client = ApiProbeClient(ROOT, output, max_attempts=max_attempts)
        result = dict(status='started', start_count=checkpoint, requests=[],
                      max_attempts=max_attempts, detail_downloads=0, evidence='PII-filtered projection, not raw response')
        seen = set()
        frontage_total = None

        def save():
            result['end_count'] = client.state['request_count']
            write_json(output / 'result.json', result)

        try:
            save()
            _, meta = client.fetch_json('https://moso.vn/robots.txt', robots=True)
            result['requests'].append(dict(meta=meta, robots_verified=True))
            save()
            for group, offset in PLAN:
                if group == 'frontage' and offset >= 940 and frontage_total is not None and offset >= frontage_total:
                    result['requests'].append(dict(group=group, offset=offset, skipped='beyond_reported_total'))
                    save()
                    continue
                value, meta = client.fetch_json(search_url(group, offset))
                record = dict(group=group, offset=offset, meta=meta, schema=schema_shape(value))
                result['requests'].append(record)
                save()  # Giữ được shape nếu adapter từ chối, không giữ giá trị PII.
                projected = project_response(value)
                parent = value
                for key in projected['list_path'][:-1]:
                    parent = parent[key]
                # Metadata chỉ là số API báo, chưa phải số tin đúng địa bàn cũ.
                total = parent.get('total') if isinstance(parent, dict) else None
                if type(total) is int and total >= 0:
                    record['reported_total_unverified'] = total
                    if group == 'frontage':
                        frontage_total = total if frontage_total is None else min(frontage_total, total)
                for item in projected['candidates']:
                    item['known_id'] = item['api_id'] in client.known_ids
                    item['known_url'] = item['url'] in client.known_urls
                    item['new_url_in_probe'] = item['url'] not in seen
                    seen.add(item['url'])
                record.update(projected)
                record['counts'] = dict(results=len(projected['candidates']),
                    unique_urls=len({item['url'] for item in projected['candidates']}),
                    known_ids=sum(item['known_id'] for item in projected['candidates']),
                    known_urls=sum(item['known_url'] for item in projected['candidates']),
                    new_urls_in_probe=sum(item['new_url_in_probe'] for item in projected['candidates']))
                save()
                print(f'{group} offset {offset}: {len(projected["candidates"])} URL; count {client.state["request_count"]}', flush=True)
            result['status'] = 'completed_discovery_only'
        except (CrawlStopped, ValueError) as exc:
            result['status'], result['error'] = 'stopped', str(exc)
        finally:
            client.session.close()
            client.state['api_probe'] = dict(result_path=(output / 'result.json').relative_to(ROOT).as_posix(),
                                            status=result['status'])
            client.save_state()
            save()
        return 0 if result['status'] == 'completed_discovery_only' else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--checkpoint', type=int)
    parser.add_argument('--max-attempts', type=int, default=20, choices=range(1, 21))
    args = parser.parse_args()
    if args.execute and args.checkpoint is None:
        parser.error('--execute cần checkpoint đã được duyệt')
    if args.execute:
        sys.exit(execute(args.checkpoint, args.max_attempts))
    prepare()
