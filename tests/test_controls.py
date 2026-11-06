import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import crawler
from src.config import COLUMNS, DISTRICTS


class FakeResponse:
    status_code = 200
    content = b'User-agent: *\nDisallow: /private\n'
    text = content.decode()
    is_redirect = False
    headers = {}


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []
        self.response = FakeResponse()

    def get(self, url, **kwargs):
        self.calls.append(url)
        return self.response


class ControlsTest(unittest.TestCase):
    def test_schema(self):
        self.assertEqual(len(COLUMNS), 23)
        self.assertEqual(len(set(COLUMNS)), 23)
        self.assertEqual(len(set(DISTRICTS)), 24)

    def test_budget_delay_robots_and_single_run(self):
        with tempfile.TemporaryDirectory(dir=crawler.ROOT) as directory:
            base = Path(directory)
            session, sleeps = FakeSession(), []
            client = crawler.ControlledClient(base, 'pilot', session, lambda: 100, sleeps.append)
            client.load_robots()
            client.fetch('https://moso.vn/allowed', 'list')
            self.assertEqual(sleeps, [1.5])
            with self.assertRaises(crawler.CrawlStopped):
                client.fetch('https://moso.vn/private', 'list')
            self.assertEqual(client.state['request_count'], 2)
            with self.assertRaises(crawler.CrawlStopped):
                crawler.ControlledClient(base, 'pilot', session)
            client.state['request_count'] = 500
            with self.assertRaises(crawler.CrawlStopped):
                client.fetch('https://moso.vn/allowed', 'list')
            self.assertEqual(len(session.calls), 2)

    def test_external_redirect_and_block(self):
        with tempfile.TemporaryDirectory(dir=crawler.ROOT) as directory:
            session = FakeSession()
            client = crawler.ControlledClient(Path(directory), 'pilot', session)
            client.load_robots()
            with self.assertRaises(crawler.CrawlStopped):
                client.fetch('https://other.example/', 'list')
            session.response = FakeResponse()
            session.response.is_redirect = True
            session.response.headers = {'Location': 'https://other.example/'}
            with self.assertRaises(crawler.CrawlStopped):
                client.fetch('https://moso.vn/allowed', 'list')
            self.assertEqual(len(session.calls), 2)
            session.response.is_redirect = False
            session.response.status_code = 429
            with self.assertRaisesRegex(crawler.CrawlStopped, 'Bị chặn'):
                client.fetch('https://moso.vn/allowed', 'list')


if __name__ == '__main__':
    unittest.main()
