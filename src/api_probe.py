"""Phép thử discovery độc lập; không tải detail hoặc sửa CSV."""
import csv
import hashlib
import json
import re
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .config import AGENT
from .crawler import ControlledClient, CrawlStopped, research_lock as probe_lock

SEARCH = 'https://moso.vn/api/agent/search'
PLAN = [(group, offset) for group in ('apartment', 'frontage', 'detached_house')
        for offset in (0, 20)] + [('frontage', 0), ('frontage', 940), ('frontage', 960)]
MAX_BYTES = 2 * 1024 * 1024


def search_url(group, offset):
    if (group, offset) not in PLAN:
        raise CrawlStopped('Bộ lọc ngoài gói thử.')
    return SEARCH + '?' + urlencode(dict(propertyType=group, offset=offset, limit=20,
                                        type='sale', location='Hồ Chí Minh', format='json'))


def validate_url(url, discovery=False):
    try:
        ControlledClient.check_url(url)
        parts = urlsplit(url)
        if parts.fragment or parts.password or 'q' in parse_qs(parts.query, keep_blank_values=True):
            raise ValueError
        if discovery and url not in {search_url(*item) for item in PLAN}:
            raise ValueError
    except (ValueError, CrawlStopped):
        raise CrawlStopped('URL bị từ chối; không ghi giá trị không tin cậy vào log.') from None


def audit(base):
    state = json.loads((base / 'data/run_state.json').read_text(encoding='utf-8'))
    with (base / 'logs/requests.csv').open(encoding='utf-8-sig', newline='') as file:
        logs = list(csv.DictReader(file))
    manifest = [json.loads(line) for line in
                (base / 'data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    if state['mode'] != 'full' or state['limit'] != 3000 or state['request_count'] != len(logs):
        raise CrawlStopped('State và request log không khớp.')
    # Từng HTTP có phản hồi phải có manifest, không chỉ so số dòng.
    responses = [row for row in logs if row['status_code']]
    if len(responses) != len(manifest):
        raise CrawlStopped('Manifest và request log không khớp.')
    for row, meta in zip(responses, manifest):
        if (row['url'], row['thoi_diem'], row['status_code']) != (
                meta['url'], meta['thoi_diem_crawl'], str(meta['status_code'])):
            raise CrawlStopped('Sai liên kết manifest/request log.')
    details = [meta for meta in manifest if meta['kind'] == 'detail']
    return state, manifest, {m['tin_id'] for m in details}, {m['url'] for m in details}


def schema_shape(value, depth=0):
    """Chỉ lưu tên field an toàn và kiểu, không lưu giá trị nội dung."""
    if depth >= 4:
        return type(value).__name__
    if isinstance(value, dict):
        return {key: schema_shape(child, depth + 1) for key, child in value.items()
                if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,39}', key)}
    if isinstance(value, list):
        return {'length': len(value), 'first_shape': schema_shape(value[0], depth + 1) if value else None}
    return type(value).__name__


def project_response(value):
    """Chưa biết schema: chỉ nhận đúng một danh sách bản ghi có URL rõ ràng.

    Không suy ID từ slug và không suy nhãn HTML từ propertyType của request.
    Tên field dưới đây là adapter thận trọng, chưa phải schema API đã chứng minh.
    """
    candidates = []

    def find(node, path, depth=0):
        if depth > 3:
            return
        if isinstance(node, list):
            if node and all(isinstance(item, dict) and isinstance(item.get('url'), str) for item in node):
                candidates.append((path, node))
        elif isinstance(node, dict):
            for key in ('data', 'results', 'listings', 'items'):
                if key in node:
                    find(node[key], path + [key], depth + 1)

    find(value, [])
    if len(candidates) != 1:
        raise CrawlStopped('Schema chưa xác minh hoặc danh sách rỗng; dừng để review cấu trúc.')
    path, rows = candidates[0]
    if len(rows) > 20:
        raise CrawlStopped('API trả quá limit 20; dừng kiểm tra.')
    result = []
    for order, row in enumerate(rows, 1):
        url = urljoin('https://moso.vn', row['url'])
        validate_url(url)
        # URL detail phải là path thuần; query có thể mang dữ liệu ngoài allowlist.
        if urlsplit(url).query or not re.fullmatch(r'/[a-zA-Z0-9_-]+', urlsplit(url).path):
            raise CrawlStopped('URL ứng viên chưa phù hợp quy tắc lưu discovery.')
        identifier = row.get('id', row.get('_id'))
        if identifier is not None and (not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{24}', identifier)):
            raise CrawlStopped('ID chưa xác minh; không lưu hoặc tạo ID thay thế.')
        result.append(dict(url=url, api_id=identifier, order=order))
    return dict(list_path=path, candidates=result)


class ApiProbeClient(ControlledClient):
    def __init__(self, base, output, transport=None, clock=time.monotonic, sleep=time.sleep, max_attempts=20):
        # Chỉ nối full hiện có, tuyệt đối không gọi constructor mở lượt mới.
        if not (base / 'data/api_probe.lock').exists():
            raise CrawlStopped('Phải giữ khóa nghiên cứu trước khi nối state.')
        self.base, self.output = base, output
        self.research_lock_owned = True
        self.state, self.manifest, self.known_ids, self.known_urls = audit(base)
        self.state_path = base / 'data/run_state.json'
        self.start_count = self.state['request_count']
        if type(max_attempts) is not int or not 1 <= max_attempts <= 20:
            raise CrawlStopped('Trần phép thử phải từ 1 đến 20; không tự nâng ngân sách.')
        self.limit = min(self.state['limit'], self.start_count + max_attempts)
        self.clock, self.sleep, self.last_end = clock, sleep, clock()
        self.session = transport or requests.Session()
        self.session.trust_env = False
        self.session.headers.update({'User-Agent': AGENT, 'Accept': 'application/json'})
        self.robot = None
        self.delay = 1.5

    def fetch_json(self, url, robots=False):
        for _ in range(6):
            validate_url(url, discovery=not robots)
            if robots and url != 'https://moso.vn/robots.txt':
                self.stop('Redirect robots ngoài route đã duyệt.')
            if not robots and (self.robot is None or not self.robot.can_fetch(AGENT, url)):
                self.stop('Robots chưa xác minh hoặc cấm URL.')
            # Phát hiện mọi ghi state/log ngoài client trước HTTP tiếp theo.
            disk, _, _, _ = audit(self.base)
            if disk != self.state:
                raise CrawlStopped('State thay đổi ngoài phép thử; không gọi mạng.')
            if self.state['request_count'] >= self.limit:
                self.stop('Chạm trần phép thử hoặc trần full.')
            self.sleep(max(0, self.delay - (self.clock() - self.last_end)))
            self.state['request_count'] += 1
            self.save_state()
            stamp = self.now()
            response, body, error = None, b'', None
            try:
                response = self.session.get(url, timeout=(15, 45), allow_redirects=False, stream=True)
                for chunk in response.iter_content(65536):
                    body += chunk
                    if len(body) > MAX_BYTES:
                        error = 'Response vượt giới hạn 2 MiB; không lưu nội dung.'
                        break
            except requests.RequestException as exc:
                error = type(exc).__name__
            finally:
                self.last_end = self.clock()
                with (self.base / 'logs/requests.csv').open('a', newline='', encoding='utf-8') as file:
                    csv.writer(file).writerow([url, stamp, '' if response is None else response.status_code])
                if response is not None:
                    response.close()
            meta = dict(url=url, thoi_diem_crawl=stamp, kind='api_probe', source='public_search_probe',
                        order=0, tin_id='', status_code=None if response is None else response.status_code,
                        content_type=('application/json' if response is not None and
                                      response.headers.get('Content-Type', '').split(';')[0].strip().lower() == 'application/json'
                                      else 'other'),
                        sha256=hashlib.sha256(body).hexdigest(), body_complete=error is None,
                        storage='not_persisted', request_number=self.state['request_count'])
            if response is not None:
                with (self.base / 'data/manifest.jsonl').open('a', encoding='utf-8') as file:
                    file.write(json.dumps(meta, ensure_ascii=False) + '\n')
            if error:
                self.stop('Phép thử dừng: ' + error + '; không retry.')
            lower = body.lower()
            if response.status_code in (403, 429) or any(marker in lower for marker in (
                    b'captcha', b'cf-chl-', b'cf-turnstile', b'verify you are human',
                    b'access denied', b'just a moment...', b'unusual traffic', b'temporarily blocked')):
                self.stop('Bị chặn; dừng toàn bộ phép thử.')
            if response.is_redirect:
                url = urljoin(url, response.headers.get('Location', ''))
                continue
            if response.status_code != 200:
                self.stop(f'HTTP {response.status_code}; không retry.')
            if robots:
                text = body.decode('utf-8-sig')
                if '<html' in text.lower() or not any(line.lower().startswith('user-agent:') for line in text.splitlines()):
                    self.stop('Robots không hợp lệ.')
                self.robot = RobotFileParser()
                self.robot.parse(text.splitlines())
                (self.output / f'robots_{self.state["request_count"]}.txt').write_bytes(body)
                self.delay = max(1.5, self.robot.crawl_delay(AGENT) or 0)
                rate = self.robot.request_rate(AGENT)
                if rate and rate.requests:
                    self.delay = max(self.delay, rate.seconds / rate.requests)
                return {'robots_verified': True}, meta
            if meta['content_type'] != 'application/json':
                self.stop('Content-Type không phải application/json.')
            try:
                value = json.loads(body)
            except (ValueError, UnicodeError):
                self.stop('JSON không hợp lệ; không ghi body vào lỗi.')
            return value, meta
        self.stop('Quá giới hạn redirect.')
