"""Nhận diện mẫu HTML do API tìm được; không gán loại từ bộ lọc API."""
import re
from urllib.parse import urlsplit

from .api_probe import validate_url
from .crawler import CrawlStopped
from .parser import flight_objects, parse_detail, soup_from_html


def identify_html(html, url):
    validate_url(url)
    soup = soup_from_html(html)
    canonical = soup.select('link[rel=canonical]')
    if len(canonical) != 1 or len(soup.find_all('h1')) != 1:
        raise CrawlStopped('Không xác định duy nhất canonical/h1 của HTML mẫu.')
    canonical_url = canonical[0].get('href', '')
    validate_url(canonical_url)
    if canonical_url != url:
        raise CrawlStopped('Canonical khác URL cuối; dừng, không tự đổi danh tính.')
    slug = urlsplit(url).path.strip('/')
    identifiers = set()
    for obj in flight_objects(soup):
        identifier = obj.get('_id')
        if not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{24}', identifier) or 'type' not in obj:
            continue
        for key in ('@page', '@newAddressPage'):
            page = obj.get(key)
            if isinstance(page, dict) and page.get('slug') == slug:
                if page.get('modelId', identifier) != identifier:
                    raise CrawlStopped('ID trang và đối tượng chính mâu thuẫn.')
                identifiers.add(identifier)
    if len(identifiers) != 1:
        raise CrawlStopped('Không tìm được duy nhất ID thật gắn với slug/canonical.')
    return identifiers.pop()


def inspect_sample(html, meta, known_ids):
    identifier = identify_html(html, meta['url'])
    parse_meta = dict(meta, tin_id=identifier)
    row, reason, evidence = parse_detail(html, parse_meta)
    eligible = not reason and evidence['semantic_eligible'] and row['loai_hinh'] in ('can_ho', 'nha_hem', 'nha_mat_tien')
    return dict(tin_id=identifier, new_id=identifier not in known_ids,
                html_type=row['loai_hinh'], district=row['quan_huyen_chuan'],
                province=evidence['province'], transaction_type=evidence['transaction_type'],
                scope_status=evidence['scope_status'], asset_unit_status=evidence['asset_unit_status'],
                exclusion_reason=reason, eligible_under_existing_rules=eligible,
                price_vnd=row['gia_vnd'], area_m2=row['dien_tich_m2'], area_type=row['loai_dien_tich'],
                parsed_column_count=len(row), missing_columns=[key for key, value in row.items() if value in ('', None)])
