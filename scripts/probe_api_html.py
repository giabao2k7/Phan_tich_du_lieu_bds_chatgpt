"""Tối đa 5 HTML nghiên cứu được duyệt; chung trần gói API 1.539."""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.robotparser import RobotFileParser

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.api_html_probe import inspect_sample
from src.api_probe import audit, probe_lock, validate_url
from src.config import AGENT, ROOT, TZ
from src.crawler import ControlledClient, CrawlStopped
from scripts.probe_api import write_json


def select_samples(result, known_urls):
    selected, seen = [], set()
    for group, limit in (('apartment', 2), ('frontage', 2), ('detached_house', 1)):
        count = 0
        for record in result['requests']:
            if record.get('group') != group:
                continue
            for item in record.get('candidates', []):
                url = item['url']
                if url in known_urls or url in seen:
                    continue
                validate_url(url)
                selected.append(dict(api_filter=group, url=url, offset=record['offset'], order=item['order']))
                seen.add(url)
                count += 1
                if count == limit:
                    break
            if count == limit:
                break
        if count != limit:
            raise CrawlStopped('Không đủ ứng viên theo cách chọn đã duyệt.')
    return selected


def run(execute=False):
    source = ROOT / 'analyses/api_probe_from_1520'
    discovery = json.loads((source / 'result.json').read_text(encoding='utf-8'))
    output = ROOT / 'analyses/api_html_probe_from_1530'
    with probe_lock(ROOT):
        state, _, known_ids, known_urls = audit(ROOT)
        if state['request_count'] != 1530 or discovery['status'] != 'completed_discovery_only':
            raise CrawlStopped('Checkpoint khác gói HTML mẫu được duyệt.')
        samples = select_samples(discovery, known_urls)
        robots_meta = discovery['requests'][0]['meta']
        robots_path = source / f'robots_{robots_meta["request_number"]}.txt'
        robots_bytes = robots_path.read_bytes()
        if hashlib.sha256(robots_bytes).hexdigest() != robots_meta['sha256']:
            raise CrawlStopped('Hash robots không khớp.')
        # Dùng lại robots cùng phiên khi tuổi không quá 24 giờ; hết hạn thì dừng để chuẩn bị lại.
        age = datetime.now(TZ) - datetime.fromisoformat(robots_meta['thoi_diem_crawl'])
        if not timedelta(0) <= age <= timedelta(hours=24):
            raise CrawlStopped('Robots quá 24 giờ hoặc timestamp bất thường; không tự tải lại.')
        robot = RobotFileParser()
        robot.parse(robots_bytes.decode('utf-8-sig').splitlines())
        if not all(robot.can_fetch(AGENT, item['url']) for item in samples):
            raise CrawlStopped('Robots cấm một URL mẫu.')
        if not execute:
            print(json.dumps(dict(samples=samples, max_http_attempts=9, max_html_samples=5,
                                  absolute_end_limit=1539, robots_reuse_max_hours=24), ensure_ascii=False, indent=2))
            return 0
        output.mkdir(exist_ok=False)
        write_json(output / 'state_before.json', state)
        result = dict(status='started', start_count=1530, absolute_end_limit=1539,
                      max_http_attempts=9, max_html_samples=5, samples=[], selected=samples,
                      robots=dict(path=robots_path.relative_to(ROOT).as_posix(), sha256=robots_meta['sha256'],
                                  max_age_hours=24), csv_integrated=False)
        client = ControlledClient.__new__(ControlledClient)
        client.base, client.mode = ROOT, 'full'
        client.state, client.state_path = state, ROOT / 'data/run_state.json'
        client.research_lock_owned = True
        client.limit = min(1539, state['limit'])
        client.clock, client.sleep, client.last_end = time.monotonic, time.sleep, time.monotonic()
        client.robot, client.delay = robot, max(1.5, robot.crawl_delay(AGENT) or 0)
        rate = robot.request_rate(AGENT)
        if rate and rate.requests:
            client.delay = max(client.delay, rate.seconds / rate.requests)
        client.session = requests.Session()
        client.session.trust_env = False
        client.session.headers.update({'User-Agent': AGENT, 'Accept': 'text/html'})

        def save():
            result['end_count'] = state['request_count']
            write_json(output / 'result.json', result)

        try:
            save()
            for index, sample in enumerate(samples, 1):
                disk, _, _, _ = audit(ROOT)
                if disk != state:
                    raise CrawlStopped('State thay đổi ngoài gói HTML; dừng trước HTTP.')
                # kind nghiên cứu để không đưa mẫu vào parse/collection chính.
                _, meta = client._fetch_locked(sample['url'], 'api_html_probe', 'api_sample', index)
                record = dict(sample, meta=meta)
                result['samples'].append(record)
                save()
                body = (ROOT / meta['html_path']).read_bytes()
                if hashlib.sha256(body).hexdigest() != meta['sha256']:
                    raise CrawlStopped('Hash HTML mẫu không khớp.')
                record.update(inspect_sample(body, meta, known_ids))
                record['new_id_in_probe'] = record['tin_id'] not in {item.get('tin_id') for item in result['samples'][:-1]}
                save()
                print(f'Mẫu {index}: ID {record["tin_id"]}; mới={record["new_id"]}; hợp lệ={record["eligible_under_existing_rules"]}', flush=True)
            result['status'] = 'completed_research_only'
        except (CrawlStopped, ValueError) as exc:
            result['status'], result['error'] = 'stopped', str(exc)
        finally:
            client.session.close()
            state['api_html_probe'] = dict(result_path=(output / 'result.json').relative_to(ROOT).as_posix(), status=result['status'])
            client.save_state()
            save()
        return 0 if result['status'] == 'completed_research_only' else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    sys.exit(run(args.execute))
