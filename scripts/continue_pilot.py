"""Nối phần khảo sát vào thu thập của cùng pilot; không tải lại URL đã lưu."""
import json
import sys
import time
from pathlib import Path
from urllib.robotparser import RobotFileParser
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, AGENT
from src.crawler import ControlledClient, CrawlStopped
from src.collection import collect


def run():
    base = ROOT / 'pilot'
    state_path = base / 'data/run_state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    manifest = [json.loads(line) for line in (base / 'data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    if state['request_count'] != 4 or state['stop_reason'] or [m['kind'] for m in manifest] != ['robots', 'list', 'list', 'list']:
        raise RuntimeError('Chỉ nối khảo sát 4 request đang mở; cấm chạy lại pilot.')
    client = ControlledClient.__new__(ControlledClient)
    client.base, client.mode, client.limit = base, 'pilot', 500
    client.state_path, client.state = state_path, state
    client.clock, client.sleep, client.last_end = time.monotonic, time.sleep, time.monotonic()
    client.session = requests.Session()
    client.session.trust_env = False
    client.session.headers.update({'User-Agent': AGENT})
    client.robot = RobotFileParser()
    client.robot.parse((ROOT / manifest[0]['html_path']).read_text(encoding='utf-8').splitlines())
    try:
        collect(client, {m['url']: m for m in manifest if m['kind'] == 'list'})
    except (CrawlStopped, ValueError) as exc:
        client.state['stop_reason'] = str(exc)
        client.save_state()
        print(str(exc), flush=True)


if __name__ == '__main__':
    run()
