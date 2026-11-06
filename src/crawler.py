import csv
import hashlib
import json
import time
from datetime import datetime
from urllib.parse import urljoin, urlsplit, parse_qs
from urllib.robotparser import RobotFileParser

import requests

from .config import ROOT, TZ, AGENT


class CrawlStopped(RuntimeError):
    pass


class ControlledClient:
    def __init__(self, base, mode, transport=None, clock=time.monotonic, sleep=time.sleep):
        self.base = base
        self.mode = mode
        self.limit = 500 if mode == 'pilot' else 3000
        self.clock, self.sleep = clock, sleep
        self.last_end = None
        self.robot = None
        self.session = transport or requests.Session()
        self.session.trust_env = False
        self.session.headers.update({'User-Agent': AGENT})
        for folder in ['data/raw_html', 'data/list_html', 'logs', 'reports', 'outputs']:
            (base / folder).mkdir(parents=True, exist_ok=True)
        self.state_path = base / 'data/run_state.json'
        if self.state_path.exists():
            raise CrawlStopped('Lượt này đã bắt đầu. Chỉ được dùng parse offline.')
        # Tạo độc quyền để hai tiến trình không thể khởi tạo cùng lượt.
        self.state = dict(mode=mode, started_at=self.now(), request_count=0,
                          limit=self.limit, stop_reason='', source_counts={})
        with self.state_path.open('x', encoding='utf-8') as file:
            json.dump(self.state, file, ensure_ascii=False, indent=2)
        with (base / 'logs/requests.csv').open('x', newline='', encoding='utf-8-sig') as file:
            csv.writer(file).writerow(['url', 'thoi_diem', 'status_code'])

    @staticmethod
    def now():
        return datetime.now(TZ).isoformat()

    def save_state(self):
        temp = self.state_path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.state_path)

    def stop(self, reason):
        self.state['stop_reason'] = reason
        self.save_state()
        raise CrawlStopped(reason)

    @staticmethod
    def check_url(url):
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname != 'moso.vn' or parts.port not in (None, 443) or parts.username:
            raise CrawlStopped('URL ngoài phạm vi https://moso.vn bị từ chối.')

    def fetch(self, url, kind, source='', order=0, tin_id=''):
        for hop in range(6):
            self.check_url(url)
            if 'q' in parse_qs(urlsplit(url).query, keep_blank_values=True):
                self.stop('Không thu thập truy vấn q; robots chặn wildcard tham số này.')
            if kind != 'robots' and (self.robot is None or not self.robot.can_fetch(AGENT, url)):
                self.stop('Robots chưa xác minh hoặc cấm URL nội dung.')
            if self.state['request_count'] >= self.limit:
                self.stop('Chạm trần request.')
            if self.last_end is not None:
                self.sleep(max(0, self.delay - (self.clock() - self.last_end)))
            self.state['request_count'] += 1
            self.save_state()
            stamp = self.now()
            response, error = None, None
            try:
                response = self.session.get(url, timeout=(15, 45), allow_redirects=False)
            except requests.RequestException as exc:
                error = type(exc).__name__
            finally:
                self.last_end = self.clock()
                with (self.base / 'logs/requests.csv').open('a', newline='', encoding='utf-8') as file:
                    csv.writer(file).writerow([url, stamp, '' if response is None else response.status_code])
            if error:
                self.stop('Không có phản hồi HTTP: ' + error + '; không retry.')
            digest = hashlib.sha256(url.encode()).hexdigest()[:24]
            import re
            reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{number}' for prefix in ['COM', 'LPT'] for number in range(1, 10)}
            safe_id = re.fullmatch(r'[a-zA-Z0-9_-]+', tin_id) and tin_id.upper() not in reserved
            name = tin_id if safe_id else hashlib.sha256(tin_id.encode()).hexdigest()
            is_detail = kind == 'detail' and not response.is_redirect
            folder = 'raw_html' if is_detail else 'list_html'
            filename = f'{name}.html' if is_detail else f'{digest}_{self.state["request_count"]}.html'
            path = self.base / 'data' / folder / filename
            if path.exists():
                self.stop('Từ chối ghi đè HTML nguồn đã tồn tại.')
            path.write_bytes(response.content)
            meta = dict(url=url, thoi_diem_crawl=stamp, html_path=path.relative_to(ROOT).as_posix(),
                        kind='redirect' if response.is_redirect else kind, source=source, order=order, tin_id=tin_id,
                        status_code=response.status_code, sha256=hashlib.sha256(response.content).hexdigest())
            with (self.base / 'data/manifest.jsonl').open('a', encoding='utf-8') as file:
                file.write(json.dumps(meta, ensure_ascii=False) + '\n')
            text = response.text
            lower = text.lower()
            blocked = any(marker in lower for marker in ['cf-chl-', 'g-recaptcha', 'hcaptcha',
                'verify you are human', 'access denied', 'just a moment...', 'captcha',
                'unusual traffic', 'temporarily blocked', 'cf-turnstile'])
            if response.status_code in (403, 429) or blocked:
                self.stop(f'Bị chặn: HTTP {response.status_code}; dừng toàn bộ.')
            if response.is_redirect:
                url = urljoin(url, response.headers.get('Location', ''))
                self.check_url(url)
                continue
            if response.status_code != 200:
                self.stop(f'HTTP {response.status_code}; không retry, cần kiểm tra nguồn đã lưu.')
            return text, meta
        self.stop('Chuyển hướng quá nhiều.')

    delay = 1.5

    def load_robots(self):
        text, _ = self.fetch('https://moso.vn/robots.txt', 'robots')
        if '<html' in text.lower() or not any(line.lower().startswith('user-agent:') for line in text.splitlines()):
            self.stop('robots.txt không có quy tắc có thể xác minh.')
        self.robot = RobotFileParser()
        self.robot.parse(text.splitlines())
        self.delay = max(1.5, self.robot.crawl_delay(AGENT) or 0)
        rate = self.robot.request_rate(AGENT)
        if rate and rate.requests:
            self.delay = max(self.delay, rate.seconds / rate.requests)
