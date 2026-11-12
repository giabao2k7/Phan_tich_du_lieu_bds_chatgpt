"""Tiếp tục từ điểm dừng được duyệt, trong cùng ngân sách full."""
import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.collection import collect
from src.config import AGENT, ROOT
from src.crawler import ControlledClient, CrawlStopped


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', type=int, help='Bộ đếm tại điểm dừng được duyệt')
    parser.add_argument('--frontage-limit', type=int, help='Giới hạn nhà mặt tiền mới đã được duyệt')
    args = parser.parse_args()
    checkpoint = args.checkpoint
    state_path = ROOT / 'data/run_state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    with (ROOT / 'logs/requests.csv').open(encoding='utf-8-sig', newline='') as file:
        logs = list(csv.DictReader(file))
    completed = state['stop_reason'] == 'Hoàn tất thu thập full'
    if args.frontage_limit is not None:
        previous_limit = state.get('source_limits', {}).get('nha_mat_tien', 926)
        if not completed or not previous_limit < args.frontage_limit <= state['limit']:
            raise RuntimeError('Chỉ nâng giới hạn đã duyệt sau khi hoàn tất lượt full.')
    elif completed:
        raise RuntimeError('Lượt full đã hoàn tất; cần giới hạn nhà mặt tiền mới được duyệt.')
    if not completed and state['stop_reason'] != 'Không có phản hồi HTTP: ConnectionError; không retry.':
        raise RuntimeError('Chỉ tiếp tục sau lỗi kết nối không có phản hồi HTTP hoặc nâng giới hạn đã duyệt.')
    successful_logs = [log for log in logs if log['status_code'] == '200']
    if (state['mode'] != 'full' or state['limit'] != 3000
            or not 0 < len(logs) == state['request_count'] == checkpoint < state['limit']
            or any(log['status_code'] not in ('', '200') for log in logs)
            or logs[-1]['status_code'] != ('200' if completed else '')):
        raise RuntimeError('Trạng thái không đủ điều kiện tiếp tục sau lỗi kết nối.')

    manifest_path = ROOT / 'data/manifest.jsonl'
    manifest = [json.loads(line) for line in manifest_path.read_text(encoding='utf-8').splitlines()]
    if len(manifest) != len(successful_logs):
        raise RuntimeError('HTML hoặc nhật ký cũ không khớp điều kiện nối lượt.')
    for index, (meta, log) in enumerate(zip(manifest, successful_logs), 1):
        if (meta['status_code'] != 200 or meta['url'] != log['url']
                or meta['thoi_diem_crawl'] != log['thoi_diem']
                or hashlib.sha256((ROOT / meta['html_path']).read_bytes()).hexdigest() != meta['sha256']):
            raise RuntimeError('HTML hoặc nhật ký cũ không khớp điều kiện nối lượt.')
        if index % 100 == 0:
            print(f'Đã kiểm tra {index}/{len(manifest)} HTML cũ.', flush=True)
    cached = {m['url']: m for m in manifest if m['kind'] == 'list'}
    details = {m['tin_id']: m for m in manifest if m['kind'] == 'detail'}
    marker = ROOT / f'data/full_continuation_{checkpoint}.json'
    with marker.open('x', encoding='utf-8') as file:
        json.dump(dict(previous_state=state, continued_at=ControlledClient.now()),
                  file, ensure_ascii=False, indent=2)
    if args.frontage_limit is not None:
        state.setdefault('source_limits', {})['nha_mat_tien'] = args.frontage_limit
    client = ControlledClient.__new__(ControlledClient)
    client.base, client.mode, client.limit = ROOT, 'full', state['limit']
    client.state_path, client.state = state_path, state
    client.clock, client.sleep, client.last_end = time.monotonic, time.sleep, time.monotonic()
    client.session = requests.Session()
    client.session.trust_env = False
    client.session.headers.update({'User-Agent': AGENT})
    state['stop_reason'] = ''
    client.save_state()
    stopped = False
    try:
        client.load_robots()
        collect(client, cached, details)
    except (CrawlStopped, ValueError) as exc:
        state['stop_reason'] = str(exc)
        client.save_state()
        print('Đã dừng phần tiếp tục:', exc, flush=True)
        stopped = True
    finally:
        client.session.close()

    return int(stopped)


if __name__ == '__main__':
    sys.exit(run())
