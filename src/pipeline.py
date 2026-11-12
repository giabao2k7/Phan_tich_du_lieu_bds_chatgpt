import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from .config import ROOT, COLUMNS, SOURCES
from .parser import parse_detail


def write_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction='raise')
        writer.writeheader()
        writer.writerows(rows)


def parse_saved(html_dir, output):
    html_dir, output = Path(html_dir).resolve(), Path(output).resolve()
    manifest_path = html_dir.parent / 'manifest.jsonl'
    if output.exists() and output.parent == html_dir.parent:
        raise ValueError('Không ghi đè CSV lịch sử; chọn thư mục đầu ra phiên bản mới.')
    if not manifest_path.exists():
        raise ValueError('Thiếu manifest.jsonl cạnh thư mục HTML; không suy metadata từ mtime.')
    manifest = [json.loads(line) for line in manifest_path.read_text(encoding='utf-8').splitlines()]
    rows, excluded, evidence_rows, errors = [], [], [], []
    seen_ids, seen_urls = set(), set()
    processed = 0
    for meta in manifest:
        if meta.get('kind') != 'detail' or meta.get('status_code') != 200:
            continue
        for key in ['url', 'thoi_diem_crawl', 'html_path', 'source', 'tin_id', 'sha256']:
            if not meta.get(key):
                raise ValueError('Thiếu metadata bắt buộc: ' + key)
        try:
            stamp = datetime.fromisoformat(meta['thoi_diem_crawl'])
            if stamp.tzinfo is None or meta['source'] not in SOURCES:
                raise ValueError('Metadata múi giờ hoặc nguồn không hợp lệ.')
            path = (ROOT / meta['html_path']).resolve()
            if not path.is_relative_to(html_dir) or not path.is_relative_to(ROOT):
                raise ValueError('HTML path nằm ngoài thư mục nguồn cho phép.')
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != meta['sha256']:
                raise ValueError('Hash HTML không khớp manifest: ' + meta['html_path'])
            row, reason, evidence = parse_detail(content, meta)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            errors.append(dict(tin_id=meta['tin_id'], reason=type(exc).__name__ + ': ' + str(exc), html_path=meta['html_path']))
            continue
        processed += 1
        if processed % 25 == 0:
            print(f'Offline: đã parse {processed} HTML.', flush=True)
        evidence['compatibility_row'] = row
        evidence_rows.append(dict(tin_id=meta['tin_id'], **evidence))
        if evidence['scope_status'] != 'supported_by_source':
            reason = 'scope_' + evidence['scope_status']
        if row['tin_id'] in seen_ids or row['url'] in seen_urls:
            reason = 'Trùng ID hoặc URL'
        if reason:
            excluded.append(dict(tin_id=row['tin_id'], reason=reason,
                                 evidence=json.dumps({'scope_status': evidence['scope_status'], 'snapshot': evidence['snapshot']}, ensure_ascii=False)))
        else:
            seen_ids.add(row['tin_id'])
            seen_urls.add(row['url'])
            rows.append(row)
    write_csv(output, rows, COLUMNS)
    base = output.parent.parent
    reports = base / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    write_csv(reports / 'exclusions.csv', excluded, ['tin_id', 'reason', 'evidence'])
    write_csv(reports / 'parse_errors.csv', errors, ['tin_id', 'reason', 'html_path'])
    from .revision_reports import report_revision
    report_revision(rows, excluded, errors, evidence_rows, base, manifest_path)
    return rows, excluded, errors
