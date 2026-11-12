import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import continue_full
from src.collection import collect


class FullExtensionTests(unittest.TestCase):
    def test_collection_preserves_default_and_uses_explicit_limit(self):
        entries = [(str(i), f'https://moso.vn/detail-{i}') for i in range(931)]
        for limits, expected in [({}, 926), ({'nha_mat_tien': 930}, 930)]:
            with self.subTest(limits=limits):
                fetched = []

                def fetch(url, kind, *args):
                    if kind == 'detail':
                        fetched.append(url)
                    return '<html></html>', {}

                client = SimpleNamespace(
                    mode='full', fetch=fetch, save_state=lambda: None,
                    state={'source_counts': {}, 'source_limits': limits, 'request_count': 0})
                with patch('src.collection.SOURCES', {'nha_mat_tien': 'https://moso.vn/list'}), \
                        patch('src.collection.list_entries', return_value=(entries, None)), \
                        patch('builtins.print'):
                    collect(client)
                self.assertEqual(len(fetched), expected)
                self.assertEqual(client.state['source_counts']['nha_mat_tien']['downloaded'], expected)

    def test_completed_run_requires_extension_and_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'logs').mkdir()
            content = b'old evidence'
            (root / 'data/old.html').write_bytes(content)
            state = dict(mode='full', limit=3000, request_count=1,
                         stop_reason='Hoàn tất thu thập full', source_counts={})
            state_path = root / 'data/run_state.json'
            state_path.write_text(json.dumps(state), encoding='utf-8')
            url, stamp = 'https://moso.vn/list', '2026-11-07T12:00:00+07:00'
            with (root / 'logs/requests.csv').open('w', encoding='utf-8-sig', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['url', 'thoi_diem', 'status_code'])
                writer.writerow([url, stamp, '200'])
            meta = dict(status_code=200, url=url, thoi_diem_crawl=stamp,
                        html_path='data/old.html', sha256=hashlib.sha256(content).hexdigest(),
                        kind='list')
            (root / 'data/manifest.jsonl').write_text(json.dumps(meta) + '\n', encoding='utf-8')
            with patch.object(continue_full, 'ROOT', root), \
                    patch('sys.argv', ['continue_full.py', '1']), \
                    self.assertRaises(RuntimeError):
                continue_full.run()
            self.assertFalse((root / 'data/full_continuation_1.json').exists())
            with patch.object(continue_full, 'ROOT', root), \
                    patch('sys.argv', ['continue_full.py', '1', '--frontage-limit', '1550']), \
                    patch.object(continue_full.ControlledClient, 'load_robots'), \
                    patch.object(continue_full, 'collect') as collector:
                self.assertEqual(continue_full.run(), 0)
            self.assertEqual(collector.call_args.args[0].state['source_limits']['nha_mat_tien'], 1550)
            marker = json.loads((root / 'data/full_continuation_1.json').read_text(encoding='utf-8'))
            self.assertEqual(marker['previous_state'], state)
            self.assertEqual(json.loads(state_path.read_text(encoding='utf-8'))['request_count'], 1)
