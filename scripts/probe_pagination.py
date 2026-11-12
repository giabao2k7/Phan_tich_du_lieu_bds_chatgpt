"""One approved probe: at most four HTTP attempts, no detail downloads or retries."""
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.robotparser import RobotFileParser

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, SOURCES, AGENT
from src.crawler import ControlledClient, CrawlStopped
from src.parser import list_entries

OUT = ROOT / 'analyses/2026-11-09_pagination_probe'
TARGETS = [('nha_hem', 19), ('nha_hem', 20), ('nha_mat_tien', 49), ('nha_mat_tien', 50)]


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    state_path = ROOT / 'data/run_state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    with (ROOT / 'logs/requests.csv').open(encoding='utf-8-sig', newline='') as f:
        logs = list(csv.DictReader(f))
    assert state['request_count'] == len(logs) == 1511
    assert state['limit'] == 3000 and state['mode'] == 'full'
    manifest = [json.loads(x) for x in (ROOT / 'data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    baseline = {source: {m['tin_id'] for m in manifest if m['kind'] == 'detail' and m['source'] == source}
                for source in ('nha_hem', 'nha_mat_tien')}
    for source, ids in baseline.items():
        assert len(ids) == state['source_counts'][source]['encountered']
    robots_meta = next(m for m in reversed(manifest) if m['kind'] == 'robots' and m['status_code'] == 200)
    robots_bytes = (ROOT / robots_meta['html_path']).read_bytes()
    assert hashlib.sha256(robots_bytes).hexdigest() == robots_meta['sha256']
    robot = RobotFileParser()
    robot.parse(robots_bytes.decode('utf-8').splitlines())
    for source, page in TARGETS:
        assert robot.can_fetch(AGENT, SOURCES[source] + f'?trang={page}')
    OUT.mkdir(exist_ok=False)
    result = dict(start_count=1511, max_http_attempts=4, baseline_counts={s: len(v) for s, v in baseline.items()},
                  baseline_definition='All saved detail IDs of same source; count equals encountered IDs in state.',
                  robots=robots_meta, pages=[], status='started')
    def save():
        result['end_count'] = state['request_count']
        (OUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    (OUT / 'state_before.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    client = ControlledClient.__new__(ControlledClient)
    client.base, client.mode, client.limit = ROOT, 'full', min(1515, state['limit'])
    client.state, client.state_path = state, state_path
    client.clock, client.sleep, client.last_end = time.monotonic, time.sleep, None
    client.robot = robot
    client.delay = max(1.5, robot.crawl_delay(AGENT) or 0)
    rate = robot.request_rate(AGENT)
    if rate and rate.requests:
        client.delay = max(client.delay, rate.seconds / rate.requests)
    client.session = requests.Session()
    client.session.trust_env = False
    client.session.headers.update({'User-Agent': AGENT})
    seen = {s: set(v) for s, v in baseline.items()}
    try:
        for source, page in TARGETS:
            url = SOURCES[source] + f'?trang={page}'
            print(f'Kiểm {source}, trang {page}; bộ đếm {state["request_count"]}', flush=True)
            html, meta = client.fetch(url, 'list', source, page)
            entries, next_url = list_entries(html, url)
            ids = [identifier for identifier, _ in entries]
            result['pages'].append(dict(source=source, page=page, meta=meta, ids=ids,
                new_vs_baseline=sorted(set(ids) - baseline[source]),
                new_in_probe=sorted(set(ids) - seen[source]), next_url=next_url))
            seen[source].update(ids)
            save()
            print(f'Đã lưu {len(ids)} ID; mới so với dữ liệu cũ: {len(set(ids) - baseline[source])}', flush=True)
        result['status'] = 'completed'
    except (CrawlStopped, ValueError, requests.RequestException) as exc:
        result['status'], result['error'] = 'stopped', str(exc)
        print('Dừng:', exc, flush=True)
    finally:
        client.session.close()
        state['pagination_probe'] = dict(result_path=str((OUT / 'result.json').relative_to(ROOT)), status=result['status'])
        client.save_state()
        save()
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    sys.exit(run())
