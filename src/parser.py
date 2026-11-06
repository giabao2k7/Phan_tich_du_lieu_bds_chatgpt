"""Đọc HTML và dữ liệu React Flight có sẵn, tuyệt đối không gọi mạng."""
import json
import re
from decimal import Decimal
from urllib.parse import urljoin
from bs4 import BeautifulSoup


def soup_from_html(html):
    soup = BeautifulSoup(html, 'lxml')
    nodes = {node['id']: node for node in soup.find_all(id=True)}
    # Ghép các mảnh HTML streaming Next.js bằng ánh xạ có trong nguồn.
    for script in soup.find_all('script'):
        for source_id, target_id in re.findall(r'\$RS\("([^"]+)","([^"]+)"\)', script.get_text()):
            source, target = nodes.get(source_id), nodes.get(target_id)
            if source is not None and target is not None:
                target.replace_with(*list(source.contents))
                source.decompose()
    return soup


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def flight_records(soup):
    chunks = []
    for script in soup.find_all('script'):
        match = re.search(r'self\.__next_f\.push\((\[.*\])\)', script.get_text(), re.S)
        if match:
            entry = json.loads(match[1])
            if len(entry) > 1 and entry[0] == 1 and isinstance(entry[1], str):
                chunks.append(entry[1])
    stream = ''.join(chunks).encode('utf-8')
    cursor = 0
    records = {}
    while cursor < len(stream):
        match = re.match(rb'[0-9a-f]*:', stream[cursor:])
        if not match:
            raise ValueError('Không giải mã được đầu dòng React Flight tại byte ' + str(cursor))
        record_id = match[0][:-1].decode()
        cursor += match.end()
        if stream[cursor:cursor+1] == b'T':
            # Dòng T đo bằng số BYTE UTF-8, không có newline kết thúc.
            end = stream.index(b',', cursor)
            length = int(stream[cursor+1:end], 16)
            records[record_id] = stream[end + 1:end + 1 + length].decode('utf-8')
            cursor = end + 1 + length
            continue
        end = stream.find(b'\n', cursor)
        if end < 0:
            end = len(stream)
        line = stream[cursor:end]
        cursor = end + 1
        if line.startswith((b'[', b'{')):
            records[record_id] = json.loads(line)
    def resolve(value, seen=frozenset()):
        if isinstance(value, str) and re.fullmatch(r'\$[0-9a-f]+(?::[^\s]+)*', value):
            if value in seen:
                return value
            parts = value[1:].split(':')
            target = records.get(parts[0], value)
            try:
                for part in parts[1:]:
                    target = target[3] if isinstance(target, list) and part == 'props' and len(target) == 4 and target[0] == '$' else target[int(part)] if isinstance(target, list) else target[part]
            except (KeyError, IndexError, TypeError, ValueError):
                return value
            return resolve(target, seen | {value})
        if isinstance(value, dict):
            return {k: resolve(v, seen) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v, seen) for v in value]
        return value
    return {key: resolve(value) for key, value in records.items()}


def located_objects(value, path):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from located_objects(child, path + ':' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from located_objects(child, path + ':' + str(index))


def flight_objects(soup):
    for value in flight_records(soup).values():
        yield from walk(value)


def detail_context(soup, tin_id):
    from .observations import SOURCE_KEYS
    candidates = [(path, obj) for key, value in flight_records(soup).items()
                  for path, obj in located_objects(value, 'Flight:' + key)
                  if obj.get('_id') == tin_id and 'type' in obj]
    if not candidates:
        raise ValueError('Không tìm thấy đối tượng khớp ID.')
    def merge(left, right, path):
        if isinstance(left, dict) and isinstance(right, dict):
            result = dict(left)
            for key, value in right.items():
                result[key] = merge(result[key], value, path + '.' + key) if key in result else value
            return result
        if left != right:
            raise ValueError('Xung đột đối tượng cùng ID tại ' + path)
        return left
    obj = {}
    for path, candidate in candidates:
        obj = merge(obj, {k: v for k, v in candidate.items() if k in SOURCE_KEYS}, path)
    headings = soup.find_all('h1')
    features = soup.select('#property-features')
    if len(headings) != 1 or len(features) != 1:
        raise ValueError('Không định danh duy nhất h1/property-features của tin chính.')
    heading = headings[0]
    if features[0].find_parent('article'):
        raise ValueError('property-features nằm trong tin gợi ý.')
    # Hai vùng đã định danh: header quanh h1 và dl#property-features.
    header = heading.parent.parent
    pairs = []
    for region, prefix in [(header, 'header[h1]'), (features[0], '#property-features')]:
        for index, term in enumerate(region.select('dt')):
            definition = term.find_next_sibling('dd')
            if definition is not None:
                pairs.append((term.get_text(strip=True), definition, f'{prefix} dt[{index}]+dd'))
    fields = {}
    for label, definition, locator in pairs:
        if label in fields and fields[label].get_text() != definition.get_text():
            if label.startswith('Diện tích'):
                continue  # Giữ tất cả trong pairs; select_area không chọn cùng đại lượng mâu thuẫn.
            raise ValueError('Nhãn DOM mâu thuẫn: ' + label)
        fields[label] = definition
    return obj, heading, fields, pairs, [p for p, _ in candidates]


def list_entries(html, url):
    soup = soup_from_html(html)
    properties = {}
    for obj in flight_objects(soup):
        if '_id' in obj:
            for key in ['@newAddressPage', '@page']:
                slug = obj.get(key, {}).get('slug')
                if slug:
                    properties[slug] = obj
    entries = []
    for article in soup.select('article'):
        link = article.select_one('h2 a[href]')
        if not link:
            raise ValueError('Có article nhưng thiếu h2 a sau ghép HTML streaming.')
        slug = link['href'].strip('/')
        obj = properties.get(slug)
        if not obj:
            raise ValueError('Không xác minh được ID thật của liên kết danh sách: ' + slug)
        entries.append((str(obj['_id']), urljoin(url, link['href'])))
    if not entries:
        raise ValueError('Không tìm thấy article; chưa xác minh đây là nguồn rỗng.')
    next_link = next((a for a in soup.select('a[href]') if a.get_text(strip=True) == 'Trang sau'), None)
    return entries, urljoin(url, next_link['href']) if next_link else None


def parse_detail(html, meta):
    from .config import COLUMNS
    from .cleaner import money, area, posting_date, district
    soup = soup_from_html(html)
    obj, heading, fields, pairs, object_paths = detail_context(soup, meta['tin_id'])
    def field(label):
        return fields[label].get_text() if label in fields else ''
    labels = {'Căn hộ chung cư': 'can_ho', 'Nhà hẻm': 'nha_hem', 'Nhà mặt tiền': 'nha_mat_tien'}
    embedded_type = {'apartment': 'can_ho', 'frontage': 'nha_mat_tien', 'alley': 'nha_hem'}
    category = (labels.get(field('Loại hình'), '') or embedded_type.get(obj.get('pTypeLvl0'), '')
                or ('nha_hem' if obj.get('pType') == 'alley_house' else ''))
    address_obj = obj.get('pAddress')
    if not isinstance(address_obj, dict):
        raise ValueError('Địa chỉ cũ không giải mã được trong đối tượng chính.')
    old_district = address_obj.get('district') or ''
    province = address_obj.get('provinceCity') or ''
    evidence = {'transaction_type': obj.get('type'), 'type_label': field('Loại hình'),
                'embedded_type': obj.get('pTypeLvl0'),
                'old_district': old_district, 'province': province, 'html_path': meta['html_path']}
    reason = ''
    if obj.get('type') != 'sale':
        reason = 'Không phải tin bán'
    elif not category:
        reason = 'Loại hình ngoài phạm vi hoặc chưa đủ bằng chứng'
    elif province not in ['Thành phố Hồ Chí Minh', 'Tp Hồ Chí Minh', 'Hồ Chí Minh']:
        reason = 'Tỉnh/thành ngoài phạm vi hoặc chưa rõ'
    elif not district(old_district):
        reason = 'Địa bàn ngoài 24 nhãn hoặc chưa đủ bằng chứng'
    row = dict.fromkeys(COLUMNS, '')
    for key in ['tin_id', 'url', 'thoi_diem_crawl', 'html_path']:
        row[key] = meta[key]
    row['loai_hinh'] = category
    row['nhom_loai_hinh'] = 'can_ho' if category == 'can_ho' else 'nha_pho' if category else ''
    price = fields.get('Mức giá')
    if price:
        spans = price.find_all('span', recursive=False)
        row['gia_goc'] = spans[0].get_text() if spans else price.get_text()
        row['gia_m2_goc'] = next((span.get_text() for span in spans[1:] if '/m²' in span.get_text()), '')
    row['gia_vnd'] = money(row['gia_goc'])
    row['gia_m2_vnd'] = money(row['gia_m2_goc'])
    from .observations import select_area, valid_coordinates, build_evidence
    chosen_area, area_reason = select_area([(label, node.get_text(), loc) for label, node, loc in pairs])
    row['dien_tich_goc'] = field(chosen_area)
    row['dien_tich_m2'] = area(row['dien_tich_goc'])
    row['loai_dien_tich'] = chosen_area.removeprefix('Diện tích ').lower() if chosen_area and chosen_area != 'Diện tích' else ''
    if row['gia_vnd'] and row['gia_vnd'] > 0 and row['dien_tich_m2'] and row['dien_tich_m2'] > 0:
        row['gia_m2_tinh_vnd'] = str(Decimal(row['gia_vnd']) / Decimal(str(row['dien_tich_m2'])))
    address = heading.parent.find('address')
    row['dia_chi_goc'] = address.get_text() if address else address_obj.get('full', '')
    # Chuỗi quận nguyên vẹn từ trường riêng trong dữ liệu nhúng, không nối chuỗi mới.
    row['quan_phuong_goc'] = old_district
    row['quan_huyen_chuan'] = district(old_district)
    coordinates = obj.get('pLocation')
    if isinstance(coordinates, dict) and coordinates.get('type') == 'Point':
        pair = coordinates.get('coordinates')
        if valid_coordinates(pair):
            row['kinh_do'], row['vi_do'] = pair
    for label, column, key in [('Số phòng ngủ', 'so_phong_ngu', 'pNumberOfBedrooms'), ('Số phòng tắm', 'so_phong_ve_sinh', 'pNumberOfBathrooms')]:
        match = re.fullmatch(r'(\d+) phòng', field(label))
        value = obj.get(key)
        row[column] = int(match[1]) if match else value if type(value) is int and value > 0 else ''
    date_tag = heading.parent.find('time')
    row['ngay_dang_goc'] = date_tag.get_text() if date_tag else ''
    row['ngay_dang'] = posting_date(row['ngay_dang_goc'], meta['thoi_diem_crawl'], date_tag.get('datetime', '') if date_tag else '')
    evidence['date_datetime_attribute'] = date_tag.get('datetime', '') if date_tag else ''
    evidence['short_id'] = obj.get('shortId', '')
    evidence['source_type'] = meta['source']
    evidence['type_disagrees_with_source'] = category != meta['source']
    evidence['embedded_price_vnd'] = obj.get('price')
    evidence['embedded_area_m2'] = obj.get('pArea')
    evidence['area_label'] = chosen_area
    evidence.update(build_evidence(obj, heading, pairs, object_paths, meta, row, area_reason))
    return row, reason, evidence
