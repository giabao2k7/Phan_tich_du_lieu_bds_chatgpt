import hashlib
from .config import ROOT, SOURCES
from .parser import list_entries
from .crawler import CrawlStopped


def collect(client, cached=None):
    cached = cached or {}
    seen_ids, seen_urls = set(), set()
    for source, first_url in SOURCES.items():
        url, page = first_url, 0
        source_ids, page_urls, contents = set(), set(), set()
        counts = dict(pages=0, encountered=0, downloaded=0, reason='')
        client.state['source_counts'][source] = counts
        while url and (client.mode == 'full' or page < 5):
            if url in page_urls:
                counts['reason'] = 'Lặp URL trang danh sách'
                break
            page_urls.add(url)
            page += 1
            if url in cached:
                html = (ROOT / cached[url]['html_path']).read_bytes()
            else:
                html, _ = client.fetch(url, 'list', source, page)
            digest = hashlib.sha256(html.encode() if isinstance(html, str) else html).hexdigest()
            if digest in contents:
                counts['reason'] = 'Lặp nội dung trang'
                break
            contents.add(digest)
            entries, next_url = list_entries(html, url)
            counts['pages'] = page
            fresh = [(identifier, link) for identifier, link in entries if identifier not in source_ids]
            if not fresh:
                counts['reason'] = 'Không còn ID mới'
                break
            for identifier, link in fresh:
                if client.mode == 'full' and source != 'can_ho' and len(source_ids) >= 926:
                    counts['reason'] = 'Đạt 926 ID duy nhất đầu tiên trước lọc'
                    break
                source_ids.add(identifier)
                counts['encountered'] = len(source_ids)
                if identifier in seen_ids or link in seen_urls:
                    continue
                seen_ids.add(identifier)
                seen_urls.add(link)
                client.fetch(link, 'detail', source, len(source_ids), identifier)
                counts['downloaded'] += 1
                client.save_state()
                print(f'{source}: trang {page}, đã tải {counts["downloaded"]}, request {client.state["request_count"]}', flush=True)
            if counts['reason']:
                break
            url = next_url
        if not counts['reason']:
            counts['reason'] = 'Hết trang' if not url else 'Đủ tối đa 5 trang pilot'
        client.save_state()
    client.state['stop_reason'] = 'Hoàn tất thu thập ' + client.mode
    client.save_state()
