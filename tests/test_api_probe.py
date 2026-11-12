import csv
import json
import tempfile
import unittest
from pathlib import Path
from urllib.robotparser import RobotFileParser
from unittest.mock import patch

import requests
from scripts import probe_api

from src.api_probe import (ApiProbeClient, PLAN, audit, probe_lock, project_response,
                           schema_shape, search_url, validate_url)
from src.config import ROOT
from src.crawler import ControlledClient, CrawlStopped


class Response:
    def __init__(self, body=b'{"items":[]}', status=200, headers=None):
        self.body, self.status_code = body, status
        self.headers = headers or {'Content-Type': 'application/json'}
        self.is_redirect = status in (301, 302, 303, 307, 308)

    def iter_content(self, size):
        yield self.body

    def close(self):
        pass


class Session:
    def __init__(self, responses):
        self.responses, self.calls, self.headers = iter(responses), [], {}

    def get(self, url, **kwargs):
        self.calls.append(url)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        pass


class ApiProbeTest(unittest.TestCase):
    def make_base(self, directory, count=0):
        base = Path(directory)
        (base / 'data').mkdir()
        (base / 'logs').mkdir()
        state = dict(mode='full', limit=3000, request_count=count, stop_reason='previous')
        (base / 'data/run_state.json').write_text(json.dumps(state), encoding='utf-8')
        with (base / 'logs/requests.csv').open('w', encoding='utf-8-sig', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['url', 'thoi_diem', 'status_code'])
            for _ in range(count):
                writer.writerow(['https://moso.vn/robots.txt', 'old', ''])
        (base / 'data/manifest.jsonl').write_text('', encoding='utf-8')
        return base

    def client(self, base, responses):
        sleeps, session = [], Session(responses)
        client = ApiProbeClient(base, base, session, lambda: 100, sleeps.append)
        client.robot = RobotFileParser()
        client.robot.parse(['User-agent: *', 'Allow: /api/agent/', 'Disallow: /api/'])
        return client, session, sleeps

    def test_url_and_real_robots_snapshot(self):
        text = (ROOT / 'data/list_html/6dcf58033e10f3e46b0d7f4e_1517.html').read_text(encoding='utf-8')
        robot = RobotFileParser()
        robot.parse(text.splitlines())
        self.assertTrue(robot.can_fetch('MosoResearch/1.0', search_url('frontage', 0)))
        self.assertFalse(robot.can_fetch('MosoResearch/1.0', 'https://moso.vn/api/private'))
        for url in ('https://moso.vn/?q=', 'https://moso.vn/?a=1&q=x',
                    'https://moso.vn/?%71=x', 'https://other.example/a',
                    'https://u@moso.vn/a', 'https://moso.vn/api',
                    'https://moso.vn/api/agent/contact'):
            with self.assertRaises(CrawlStopped):
                validate_url(url, discovery=True)
        self.assertEqual(len(PLAN), 9)

    def test_projection_drops_pii_and_does_not_map_detached_house(self):
        value = {'data': {'items': [dict(url='/tin-ban-test', id='a' * 24,
                  owner='private-person', phone='private-phone', address='private-address')]}}
        result = project_response(value)
        self.assertEqual(set(result['candidates'][0]), {'url', 'api_id', 'order'})
        self.assertNotIn('private-', json.dumps(result) + json.dumps(schema_shape(value)))
        for bad in ({'count': 50}, {'items': []}, {'items': [{'url': 'https://evil.example/a'}]},
                    {'items': [{'url': '/a?email=private'}]},
                    {'items': [{'url': '/a', 'id': 'phone-number'}]},
                    {'items': [{'url': '/a'}], 'results': [{'url': '/b'}]}):
            with self.assertRaises(CrawlStopped):
                project_response(bad)

    def test_delay_budget_and_no_raw_storage(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = self.make_base(directory, 2999)
            with probe_lock(base):
                client, session, sleeps = self.client(base, [Response(b'{"owner":"private-person"}')])
                client.fetch_json(search_url('frontage', 0))
                with self.assertRaises(CrawlStopped):
                    client.fetch_json(search_url('frontage', 20))
                self.assertEqual(len(session.calls), 1)
                self.assertEqual(sleeps, [1.5])
                self.assertEqual(audit(base)[0]['request_count'], 3000)
                for path in base.rglob('*'):
                    if path.is_file():
                        self.assertNotIn('private-person', path.read_text(encoding='utf-8-sig'))
                self.assertFalse(list(base.rglob('*.html')))

    def test_redirect_block_error_and_no_retry(self):
        cases = [([Response(status=302, headers={'Location': 'https://other.example/a'})], 1),
                 ([Response(status=302, headers={'Location': search_url('frontage', 20)}), Response()], 2),
                 ([Response(status=429)], 1), ([Response(b'captcha')], 1),
                 ([requests.ConnectionError('private-text')], 1),
                 ([Response(b'bad-json')], 1), ([Response(status=500)], 1)]
        for responses, expected in cases:
            with self.subTest(expected=expected, responses=len(responses)):
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    base = self.make_base(directory)
                    with probe_lock(base):
                        client, session, _ = self.client(base, responses)
                        if expected == 2:
                            client.fetch_json(search_url('frontage', 0))
                        else:
                            with self.assertRaises(CrawlStopped):
                                client.fetch_json(search_url('frontage', 0))
                        self.assertEqual(len(session.calls), expected)
                        self.assertEqual(audit(base)[0]['request_count'], expected)

    def test_lock_and_state_disagreement_fail_before_network(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = self.make_base(directory)
            with probe_lock(base):
                with self.assertRaises(CrawlStopped):
                    with probe_lock(base):
                        pass
                client, session, _ = self.client(base, [])
                legacy = ControlledClient.__new__(ControlledClient)
                legacy.base = base
                with self.assertRaises(CrawlStopped):
                    legacy.fetch(search_url('frontage', 0), 'list')
                with self.assertRaises(CrawlStopped):
                    legacy.save_state()
                state = json.loads(client.state_path.read_text(encoding='utf-8'))
                state['request_count'] += 1
                client.state_path.write_text(json.dumps(state), encoding='utf-8')
                with self.assertRaises(CrawlStopped):
                    client.fetch_json(search_url('frontage', 0))
                self.assertEqual(session.calls, [])

    def test_twenty_attempt_cap_and_unknown_schema_stop(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = self.make_base(directory)
            with probe_lock(base):
                client, session, _ = self.client(base, [Response()] * 20)
                for _ in range(20):
                    client.fetch_json(search_url('frontage', 0))
                with self.assertRaises(CrawlStopped):
                    client.fetch_json(search_url('frontage', 0))
                self.assertEqual(len(session.calls), 20)
                self.assertEqual(audit(base)[0]['request_count'], 20)

    def test_fresh_robots_and_response_size_limit(self):
        for response, robots in (
                (Response(b'User-agent: *\nAllow: /api/agent/\nDisallow: /api/\n'), True),
                (Response(b'x' * (2 * 1024 * 1024 + 1)), False)):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                base = self.make_base(directory)
                with probe_lock(base):
                    client, session, _ = self.client(base, [response])
                    if robots:
                        client.fetch_json('https://moso.vn/robots.txt', robots=True)
                        self.assertTrue(client.robot.can_fetch('MosoResearch/1.0', search_url('frontage', 0)))
                        self.assertEqual((base / 'robots_1.txt').read_bytes(), response.body)
                    else:
                        with self.assertRaises(CrawlStopped):
                            client.fetch_json(search_url('frontage', 0))
                    self.assertEqual(audit(base)[0]['request_count'], 1)

    def test_runner_saves_projection_skips_deep_offsets_and_stops_unknown_schema(self):
        for valid in (True, False):
            with self.subTest(valid=valid):
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    base = self.make_base(directory)
                    (base / 'analyses').mkdir()
                    robots = Response(b'User-agent: *\nAllow: /api/agent/\nDisallow: /api/\n')
                    body = (b'{"total":2,"items":[{"url":"/listing-test","owner":"private-person"}]}'
                            if valid else b'{"owner":"private-person","unknown":true}')
                    session = Session([robots] + [Response(body)] * 7)
                    with patch.object(probe_api, 'ROOT', base), \
                            patch('src.api_probe.requests.Session', return_value=session), \
                            patch('src.api_probe.ApiProbeClient.delay', 0), \
                            patch('src.api_probe.time.sleep'), patch('builtins.print'):
                        # Defaults bind time.sleep at import time; inject a non-blocking clock explicitly.
                        original_init = ApiProbeClient.__init__

                        def init(client, root, output, max_attempts=20):
                            original_init(client, root, output, session, lambda: 100, lambda _: None, max_attempts)

                        with patch.object(ApiProbeClient, '__init__', init):
                            code = probe_api.execute(0)
                    output = base / 'analyses/api_probe_from_0/result.json'
                    result = json.loads(output.read_text(encoding='utf-8'))
                    self.assertEqual(code, 0 if valid else 1)
                    self.assertEqual(len(session.calls), 8 if valid else 2)
                    self.assertEqual(audit(base)[0]['request_count'], len(session.calls))
                    self.assertNotIn('private-person', output.read_text(encoding='utf-8'))
                    if valid:
                        self.assertEqual(sum('skipped' in item for item in result['requests']), 2)
                    self.assertFalse((base / 'data/api_probe.lock').exists())

    def test_continuation_keeps_remaining_nineteen_attempts(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = self.make_base(directory, 1520)
            with probe_lock(base):
                session = Session([Response()] * 19)
                client = ApiProbeClient(base, base, session, lambda: 100, lambda _: None, max_attempts=19)
                client.robot = RobotFileParser()
                client.robot.parse(['User-agent: *', 'Allow: /api/agent/', 'Disallow: /api/'])
                self.assertEqual(client.limit, 1539)
                for _ in range(19):
                    client.fetch_json(search_url('frontage', 0))
                with self.assertRaises(CrawlStopped):
                    client.fetch_json(search_url('frontage', 0))
                self.assertEqual(len(session.calls), 19)
                self.assertEqual(audit(base)[0]['request_count'], 1539)


if __name__ == '__main__':
    unittest.main()
