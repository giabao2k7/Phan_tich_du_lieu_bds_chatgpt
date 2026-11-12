"""Hợp đồng D1–D8: chỉ quan sát trường BĐS cho phép, không xuất đối tượng liên hệ."""
import math
import re
from decimal import Decimal
from .cleaner import area, money, district

RULE_VERSION = 'D1-D8/offline-v2.1'
SOURCE_KEYS = {'_id', 'type', 'pType', 'pTypeLvl0', 'pAddress', 'newPropertyAddress',
               'pLocation', 'pArea', 'pLandArea', 'pGrossFloorArea', 'price',
               'pNumberOfBedrooms', 'pNumberOfBathrooms', 'pNumberOfFloors',
               'description', 'aiDescription', 'pProjectName', '_project_name',
               'status', 'listingStatus', 'verificationStatus', '_publishedAt',
               '_expiredAt', '_firstPublishedAt', 'shortId'}
AREA_TYPES = {'Diện tích thông thủy': 'thông thủy', 'Diện tích tim tường': 'tim tường',
              'Diện tích đất': 'đất', 'Diện tích đất công nhận': 'đất công nhận',
              'Diện tích sử dụng': 'sử dụng'}


def valid_coordinates(pair):
    return (isinstance(pair, list) and len(pair) == 2
            and all(type(x) in (int, float) and math.isfinite(x) for x in pair)
            and -180 <= pair[0] <= 180 and -90 <= pair[1] <= 90)


def haversine(a, b):
    lng1, lat1, lng2, lat2 = map(math.radians, [*a, *b])
    value = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lng2-lng1)/2)**2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, value)))


def select_area(pairs):
    values = [(label, area(raw)) for label, raw, _ in pairs
              if label == 'Diện tích' or label in AREA_TYPES]
    by_label = {}
    for label, value in values:
        if value is not None and value > 0:
            by_label.setdefault(label, set()).add(value)
    if any(len(v) > 1 for v in by_label.values()):
        return '', 'same_quantity_conflict'
    generic = next(iter(by_label.get('Diện tích', set())), None)
    specific = [(label, next(iter(v))) for label, v in by_label.items() if label != 'Diện tích']
    matching = [label for label, value in specific if value == generic]
    if generic is not None:
        return (matching[0], 'unique_specific_equal_generic') if len(matching) == 1 else ('Diện tích', 'generic_ambiguous_types' if matching else 'generic_only_or_distinct')
    if len(specific) == 1:
        return specific[0][0], 'unique_specific'
    return '', 'multiple_quantities_no_generic' if specific else 'missing_dom_area'


def value_state(raw, present=True):
    if not present:
        return 'missing'
    if raw is None:
        return 'null'
    if isinstance(raw, str) and raw.startswith('$'):
        return 'reference'
    if type(raw) in (int, float) and raw == 0:
        return 'zero'
    return 'observed'


def build_evidence(obj, heading, pairs, paths, meta, row, area_reason):
    observations = []
    snapshot = {'tin_id': meta['tin_id'], 'capture_at': meta['thoi_diem_crawl'],
                'html_sha256': meta['sha256'], 'html_path': meta['html_path']}
    def add(quantity, raw, locator, normalized=None, unit='', method='identity', present=True):
        obs_id = f'{meta["tin_id"]}:{len(observations):03}'
        observations.append(dict(snapshot, observation_id=obs_id, quantity=quantity,
                                 raw_value=raw, raw_unit=unit, locator=locator,
                                 value_state=value_state(raw, present), normalized=normalized,
                                 normalization_method=method))
        return obs_id
    for label, node, locator in pairs:
        if label.startswith('Diện tích'):
            raw = node.get_text()
            add(label, raw, locator, area(raw), 'm²' if 'm²' in raw else 'm2' if 'm2' in raw else '', 'area_regex')
        elif label in ['Loại hình', 'Số phòng ngủ', 'Số phòng tắm', 'Địa chỉ chi tiết', 'Tên dự án / tòa nhà']:
            add(label, node.get_text(), locator)
    source_path = '|'.join(paths)
    def source(key):
        return source_path + ' -> ' + key
    for key in ['pArea', 'pLandArea', 'pGrossFloorArea', 'price', 'type', 'pType', 'pTypeLvl0',
                'pNumberOfBedrooms', 'pNumberOfBathrooms', 'pNumberOfFloors', 'pProjectName',
                'status', 'listingStatus', 'verificationStatus', '_publishedAt', '_expiredAt', '_firstPublishedAt']:
        raw = obj.get(key)
        add(key, raw, source(key), raw, method='source_name_only', present=key in obj)
    addresses = {}
    for key in ['pAddress', 'newPropertyAddress']:
        addresses[key] = obj.get(key) if isinstance(obj.get(key), dict) else {}
        for field in ['full', 'streetNumber', 'streetName', 'ward', 'district', 'provinceCity', 'coordinates']:
            raw = addresses[key].get(field)
            add(key + '.' + field, raw, source(key + '.' + field), raw, present=field in addresses[key])
    pins = [('pLocation.coordinates', obj.get('pLocation', {}).get('coordinates') if isinstance(obj.get('pLocation'), dict) else obj.get('pLocation'))]
    pins += [(key + '.coordinates', value.get('coordinates')) for key, value in addresses.items()]
    add('pLocation.coordinates', pins[0][1], source('pLocation.coordinates'), pins[0][1], method='lng_lat_no_correction')
    comparisons = []
    for i, (left_path, left) in enumerate(pins):
        for right_path, right in pins[i+1:]:
            if valid_coordinates(left) and valid_coordinates(right) and left != right:
                distance = haversine(left, right)
                comparisons.append(dict(left=left_path, right=right_path, distance_m=distance,
                                        priority='low_numeric_difference' if distance <= 1 else 'review',
                                        meaning='internal_difference_not_ground_truth'))
    description = obj.get('description') or ''
    if not isinstance(description, str):
        description = ''
    # Chỉ xuất đoạn khớp ngữ cảnh BĐS; không xuất toàn bộ mô tả có thể chứa liên hệ.
    patterns = [r'DTCN\s*:\s*\d+[.,]?\d*\s*m[²2]?', r'\bDT\s*:\s*\d+[.,]?\d*\s*m\s*[x×]\s*\d+[.,]?\d*\s*m',
                r'\b\d+\s*(?:Lầu|PN)\b', r'Căn hộ\s+[^\n–—,🔥]{2,65}(?=\s*[–—])',
                r'trục\s+(?:đường\s+)?[^\n,…]{2,45}']
    excerpts = []
    for pattern in patterns:
        for match in re.finditer(pattern, description, re.I):
            excerpt = match.group()
            excerpts.append(excerpt)
            add('description_excerpt', excerpt, source(f'description[{match.start()}:{match.end()}]'))
    project_phrase = re.search(patterns[3], description, re.I)
    road_phrase = re.search(patterns[4], description, re.I)
    street = addresses['pAddress'].get('streetName') or ''
    project_text = re.sub(r'^căn hộ\s+', '', project_phrase.group(), flags=re.I).strip() if project_phrase else ''
    named_project = bool(project_text and project_text[0].isupper() and len(project_text.split()) <= 6)
    project_road_question = bool(named_project and road_phrase and street and street.casefold() not in road_phrase.group().casefold())
    old, new = addresses.values()
    compare_text = lambda value: ' '.join(str(value).split()).casefold()
    address_question = any(old.get(k) and new.get(k) and compare_text(old[k]) != compare_text(new[k]) for k in ['streetName', 'streetNumber'])
    province = old.get('provinceCity') or ''
    old_district = old.get('district') or ''
    scope = 'supported_by_source' if district(old_district) and province in ['Thành phố Hồ Chí Minh', 'Tp Hồ Chí Minh', 'Hồ Chí Minh'] else 'out_by_source' if old_district or province not in ['', 'Thành phố Hồ Chí Minh', 'Tp Hồ Chí Minh', 'Hồ Chí Minh'] else 'unresolved'
    if project_road_question or address_question:
        scope = 'conflicted'
    land = obj.get('pLandArea')
    asset_question = row['loai_hinh'] == 'can_ho' and ((type(land) in (int, float) and land > 0 and not row['dien_tich_m2']) or bool(re.search(r'\b[3-9]\d*\s*lầu\b', description, re.I)))
    asset_status = 'unresolved' if asset_question or not row['loai_hinh'] else 'supported_by_source'
    internal = 'conflicted' if area_reason == 'same_quantity_conflict' or any(c['distance_m'] > 1 for c in comparisons) or address_question or project_road_question else 'numeric_difference' if comparisons else 'no_conflict_detected'
    decisions = []
    def decide(field, selected, obs, reason, status='selected', unknown='source_not_externally_verified'):
        decisions.append(dict(snapshot, field=field, selected_value=selected,
                              candidates=obs, reason_code=reason, rule_version=RULE_VERSION,
                              status=status, unknown=unknown))
    area_obs = [o['observation_id'] for o in observations if o['quantity'].startswith('Diện tích') or o['quantity'] in ['pArea', 'pLandArea', 'pGrossFloorArea']]
    decide('compatibility_area', {'raw': row['dien_tich_goc'], 'value': row['dien_tich_m2'], 'type': row['loai_dien_tich']}, area_obs, area_reason, 'unresolved' if not row['dien_tich_m2'] else 'selected')
    for raw_col, col in [('gia_goc', 'gia_vnd'), ('gia_m2_goc', 'gia_m2_vnd')]:
        obs_id = add(raw_col, row[raw_col], 'header[h1] dt[Mức giá]+dd/' + raw_col, row[col], 'VND', 'decimal_money_strict')
        decide(col, row[col], [obs_id], 'strict_money' if row[col] is not None else 'missing_negotiable_or_ambiguous', 'selected' if row[col] is not None else 'unresolved')
    decide('gia_m2_tinh_vnd', row['gia_m2_tinh_vnd'], area_obs, 'compatibility_arithmetic_only_not_semantic_price_per_m2')
    for col, locator, method in [('loai_hinh', 'DOM:Loại hình/JSON:pTypeLvl0,pType', 'explicit_type_mapping'),
            ('dia_chi_goc', 'header[h1] address', 'identity_including_ui_text'),
            ('quan_phuong_goc', source('pAddress.district'), 'identity_district_only_ward_separate'),
            ('quan_huyen_chuan', source('pAddress.district'), 'closed_24_labels_no_ward_inference'),
            ('ngay_dang_goc', 'header[h1] time', 'identity'),
            ('ngay_dang', 'header[h1] time/text,datetime', 'relative_capture_+07_first_datetime_fallback'),
            ('so_phong_ngu', 'DOM:Số phòng ngủ/JSON:pNumberOfBedrooms', 'explicit_room_count'),
            ('so_phong_ve_sinh', 'DOM:Số phòng tắm/JSON:pNumberOfBathrooms', 'bathroom_proxy_not_confirmed_wc')]:
        raw = row[col]
        if col == 'loai_hinh':
            raw = next((node.get_text() for label, node, _ in pairs if label == 'Loại hình'), obj.get('pTypeLvl0') or obj.get('pType'))
        elif col == 'quan_huyen_chuan':
            raw = old_district
        elif col == 'ngay_dang':
            raw = row['ngay_dang_goc']
        elif col in ['so_phong_ngu', 'so_phong_ve_sinh']:
            label = 'Số phòng ngủ' if col == 'so_phong_ngu' else 'Số phòng tắm'
            raw = next((node.get_text() for name, node, _ in pairs if name == label), obj.get('pNumberOfBedrooms' if col == 'so_phong_ngu' else 'pNumberOfBathrooms'))
        oid = add(col, raw, locator, row[col], method=method)
        decide(col, row[col], [oid], method)
    time = heading.parent.find('time')
    add('time.datetime', time.get('datetime') if time else None, 'header[h1] time@datetime')
    for col in ['tin_id', 'url', 'thoi_diem_crawl', 'html_path']:
        oid = add(col, meta[col], 'manifest.' + col, meta[col])
        decide(col, row[col], [oid], 'D1_capture_manifest_identity')
    decide('nhom_loai_hinh', row['nhom_loai_hinh'], [o['observation_id'] for o in observations if o['quantity'] == 'loai_hinh'], 'D2_category_group_mapping')
    decide('coordinates', pins[0][1] if valid_coordinates(pins[0][1]) else None,
           [o['observation_id'] for o in observations if o['quantity'].endswith('coordinates')], 'pLocation_source_only_no_geocoding')
    decide('scope', scope, [o['observation_id'] for o in observations if o['quantity'].startswith(('pAddress.', 'newPropertyAddress.', 'description_'))],
           'project_road_candidate' if project_road_question else 'old_new_address_conflict' if address_question else 'historical_district_source_only', scope)
    decide('asset_unit', asset_status, area_obs, 'apartment_land_or_multifloor_question' if asset_question else 'source_type_only', asset_status)
    # Giá trị 0 vẫn ở quan sát, không dùng làm mẫu số.
    analytical = []
    for label, kind in AREA_TYPES.items():
        candidates = [o for o in observations if o['quantity'] == label and o['normalized'] is not None and o['normalized'] > 0]
        values = {o['normalized'] for o in candidates}
        eligible = scope == 'supported_by_source' and asset_status == 'supported_by_source' and obj.get('type') == 'sale'
        if len(values) == 1:
            value = next(iter(values))
            analytical.append(dict(snapshot, loai_hinh=row['loai_hinh'], area_type=kind, area_m2=value,
                                   price_vnd=row['gia_vnd'], price_per_m2_vnd=str(Decimal(row['gia_vnd'])/Decimal(str(value))) if row['gia_vnd'] else '',
                                   eligible=eligible, primary=kind == ('thông thủy' if row['loai_hinh'] == 'can_ho' else 'đất công nhận'),
                                   observation_ids=[o['observation_id'] for o in candidates]))
    return dict(observations=observations, decisions=decisions, analytical_areas=analytical,
                snapshot=snapshot, object_paths=paths, coordinate_comparisons=comparisons,
                extraction_status='parsed', internal_consistency=internal, scope_status=scope,
                asset_unit_status=asset_status, coordinate_verification='unverified' if valid_coordinates(pins[0][1]) else 'missing_or_invalid',
                availability_status='current_unknown', description_excerpts=excerpts,
                semantic_eligible=scope == 'supported_by_source' and asset_status == 'supported_by_source' and obj.get('type') == 'sale')
