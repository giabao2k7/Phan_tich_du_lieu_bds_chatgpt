"""Tiếp nối khảo sát robots của pilot đang mở; không khởi tạo lượt mới."""
import json
import sys
from pathlib import Path
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, SOURCES
from src.crawler import ControlledClient, CrawlStopped
import requests
import time


def continue_open_survey():
    base = ROOT / 'pilot'
    state = json.loads((base / 'data/run_state.json').read_text(encoding='utf-8'))
    manifest = [json.loads(line) for line in (base / 'data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    if state['request_count'] != 1 or state['stop_reason'] or len(manifest) != 1 or manifest[0]['kind'] != 'robots':
        raise RuntimeError('Chỉ tiếp nối khảo sát robots đầu tiên, không chạy lại pilot.')
    client = ControlledClient.__new__(ControlledClient)
    client.base, client.mode, client.limit = base, 'pilot', 500
    client.state_path, client.state = base / 'data/run_state.json', state
    client.clock, client.sleep, client.last_end = time.monotonic, time.sleep, time.monotonic()
    client.session = requests.Session()
    client.session.trust_env = False
    from src.config import AGENT
    client.session.headers.update({'User-Agent': AGENT})
    client.robot = RobotFileParser()
    client.robot.parse((ROOT / manifest[0]['html_path']).read_text(encoding='utf-8').splitlines())
    try:
        for source, url in SOURCES.items():
            _, meta = client.fetch(url, 'list', source, 1)
            print(meta['html_path'], flush=True)
    except CrawlStopped as exc:
        print(str(exc), flush=True)


if __name__ == '__main__':
    continue_open_survey()
