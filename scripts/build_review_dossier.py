"""Lập bằng chứng bàn giao OFFLINE, không sửa parser/CSV/HTML của pilot."""
import csv
import hashlib
import json
import math
import re
import shutil
import socket
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, TZ
from src.parser import soup_from_html, flight_objects, parse_detail

DEST = ROOT / 'handoff/2026-11-02_review'
FEEDBACK = [
    ('6ae798b72cdb82e3b72068cc', 1, 'Tọa độ', 'Lệch 70 m', 70),
    ('6ae76a572cdb82e3b7141af4', 2, 'Tọa độ', 'Lệch 1,3 km theo đường chim bay', 1300),
    ('6ad98e4c63be9ff37837ab2e', 3, 'Tọa độ', 'Lệch 4 km, mô tả chi tiết ghi Căn hộ Opal Boulevard thì nó ở Đ. Phạm Văn Đồng, Dĩ An, Hồ Chí Minh, Việt Nam, nhưng địa chỉ lại ghi khác', 4000),
    ('6ae45114bfaa4b4f2be2e31d', 5, 'Tọa độ', 'Lệch 883 m', 883),
    ('6ae2b887575dffe7bf6cef1e', 7, 'Tọa độ', 'Lệch 757 m', 757),
    ('6ae2aafdfaae27449455b5de', 8, 'Tọa độ', 'Lệch 140 m', 140),
    ('6ae29887faae274494541131', 9, 'Diện tích', 'Web thiếu thẻ diện tích (crawl ra “Không có”); phần mô tả chi tiết ghi 168 m²', None),
    ('6ae802e22cdb82e3b72c3637', 11, 'Tọa độ', 'Lệch 970 m', 970),
    ('6ae7fa572cdb82e3b72b4f4a', 12, 'Tọa độ', 'Không xác minh được', None),
    ('6ae7f74f2cdb82e3b72b05c2', 16, 'Không xác định (toàn bộ tin)', 'Tin không còn trên trang, không thể kiểm chứng', None),
    ('6ae7f05b2cdb82e3b72a2b18', 19, 'Không xác định (toàn bộ tin)', 'Tin không còn trên trang, không thể kiểm chứng', None),
    ('6ae7ee832cdb82e3b729d302', 25, 'Tọa độ', 'Lệch 840 m', 840),
    ('6ae7e20e2cdb82e3b728b048', 27, 'Không xác định (toàn bộ tin)', 'Tin không còn trên trang, không thể kiểm chứng', None),
]


def no_network(*args, **kwargs):
    raise RuntimeError('Hồ sơ này chỉ đọc offline, cấm mở socket.')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_read(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        return list(csv.DictReader(file))


def csv_write(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def json_write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def coordinate(value):
    if isinstance(value, dict):
        value = value.get('coordinates')
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        return value
    return None


def distance(first, second):
    lon1, lat1, lon2, lat2 = map(math.radians, first + second)
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371008.8 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1-a)))


def safe_address(value):
    if not isinstance(value, dict):
        return value
    keys = ['full', 'placeName', 'buildingName', 'streetNumber', 'streetName', 'ward', 'district', 'provinceCity', 'country', 'coordinates']
    return {key: value.get(key) for key in keys if key in value}


def excerpts(obj):
    result = []
    for field in ['description', 'manualDescription', 'aiDescription', 'generatedSummaryV2']:
        value = obj.get(field)
        if not isinstance(value, str) or value.startswith('$'):
            continue
        text = soup_from_html(value).get_text(' ', strip=True)
        for pattern in [r'Căn hộ Opal Boulevard[^\n.!]{0,85}', r'DTCN\s*:\s*168\s*m(?:²|2)?', r'DT\s*:\s*8m\s*x\s*21m', r'KC\s*:\s*8\s*Lầu,\s*23PN']:
            match = re.search(pattern, text, re.I)
            if match:
                snippet = match[0]
                if not re.search(r'\d{8,}|@|https?://', snippet):
                    result.append(dict(field=field, exact_excerpt=snippet,
                        meaning='Trích ngắn nguyên văn; không tự gán độ tin cậy hoặc loại diện tích.'))
    return result


def make_case_file(case):
    item = case.get('user_feedback')
    lines = [f'# Tin {case["tin_id"]}', '', '## Nguồn và định danh', '',
             f'- URL lúc tải: {case["capture"]["url"]}',
             f'- Thời điểm tải: {case["capture"]["thoi_diem_crawl"]}',
             f'- HTTP lúc tải: {case["capture"]["status_code"]}',
             f'- HTML gốc trong dự án: `{case["capture"]["html_path"]}`',
             f'- SHA-256: `{case["capture"]["sha256"]}`',
             '- Tọa độ là [kinh độ, vĩ độ]. Chưa có tọa độ thật đối chứng.', '']
    if item:
        lines += ['## Phản hồi người dùng', '', f'- STT do người dùng ghi: {item["user_stt"]}; dòng dữ liệu CSV hiện tại: {case["csv_data_row"]}.',
                  f'- Trường: {item["field"]}. Nội dung: {item["note"]}.',
                  ('- Khoảng cách do người dùng báo; không phải phép đo độc lập của agent.'
                   if item['reported_distance_m'] is not None else
                   '- Phản hồi trên chưa được xác minh bằng nguồn ngoài; bằng chứng snapshot được ghi riêng bên dưới.'), '']
    else:
        lines += [case.get('reason_for_additional_case') or 'Tin bổ sung từ báo cáo loại trừ/cảnh báo sẵn có, không nằm trong bảng 13 tin của người dùng.', '']
    lines += ['## Giá trị trong CSV', '', '```json', json.dumps(case['csv_record'], ensure_ascii=False, indent=2), '```', '',
              '## Trường gốc được phép trích trong HTML', '', '```json',
              json.dumps(case['source_fields'], ensure_ascii=False, indent=2), '```', '',
              '## Bằng chứng mô tả ngắn', '', '```json', json.dumps(case['description_excerpts'], ensure_ascii=False, indent=2), '```', '',
              '## Kết quả đối chiếu kỹ thuật', '', '```json', json.dumps(case['checks'], ensure_ascii=False, indent=2), '```', '',
              'Các kiểm tra trên chỉ so CSV với HTML đã lưu. Không xác định vị trí thật, tính chính xác của mô tả hoặc trạng thái website hiện tại.', '']
    (DEST / 'evidence/cases' / f'{case["tin_id"]}.md').write_text('\n'.join(lines), encoding='utf-8')


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    socket.socket = no_network
    socket.create_connection = no_network
    for directory in ['evidence/cases', 'snapshot/src', 'snapshot/tests', 'snapshot/pilot/reports', 'snapshot/pilot/data', 'snapshot/pilot/logs', 'snapshot/reports', 'snapshot/pilot/outputs']:
        (DEST / directory).mkdir(parents=True, exist_ok=True)
    protected = ['pilot/data/listings.csv', 'pilot/data/manifest.jsonl', 'pilot/data/run_state.json', 'pilot/logs/requests.csv',
                 'src/parser.py', 'src/cleaner.py', 'src/config.py', 'src/crawler.py', 'src/quality.py']
    before = {path: sha(ROOT / path) for path in protected}
    listings = csv_read(ROOT / 'pilot/data/listings.csv')
    by_id = {row['tin_id']: row for row in listings}
    row_numbers = {row['tin_id']: number for number, row in enumerate(listings, 1)}
    manifest = [json.loads(line) for line in (ROOT / 'pilot/data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    feedback_rows = [dict(tin_id=identifier, user_stt=stt, field=field, note=note, reported_distance_m=meters,
                          provenance='Phản hồi người dùng trong chat; chưa có tọa độ đối chứng/ảnh chụp/thời điểm kiểm tra')
                     for identifier, stt, field, note, meters in FEEDBACK]
    csv_write(DEST / 'evidence/user_feedback.csv', feedback_rows, list(feedback_rows[0]))
    feedback_by_id = {row['tin_id']: row for row in feedback_rows}
    excluded = csv_read(ROOT / 'pilot/reports/exclusions.csv')
    price_flags = [row for row in csv_read(ROOT / 'pilot/reports/quality_flags.csv') if row['issue'] == 'Chênh lệch >10%']
    case_ids = set(feedback_by_id) | {r['tin_id'] for r in excluded + price_flags}
    case_records, audit_rows, coordinate_groups = [], [], defaultdict(list)
    mismatch_fields = []
    for index, meta in enumerate(m for m in manifest if m['kind'] == 'detail'):
        path = ROOT / meta['html_path']
        content = path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        assert actual_hash == meta['sha256'], f'HTML đã thay đổi: {meta["tin_id"]}'
        soup = soup_from_html(content)
        objects = [obj for obj in flight_objects(soup) if obj.get('_id') == meta['tin_id'] and 'type' in obj]
        obj = max(objects, key=len)
        parsed, reason, _ = parse_detail(content, meta)
        saved = by_id.get(meta['tin_id'])
        differing = []
        if saved:
            for key, value in parsed.items():
                expected = '' if value is None else str(value)
                if saved[key] != expected:
                    differing.append(key)
                    mismatch_fields.append(dict(tin_id=meta['tin_id'], field=key, csv_value=saved[key], replay_value=expected))
        pin = coordinate(obj.get('pLocation'))
        old_address = obj.get('pAddress')
        new_address = obj.get('newPropertyAddress')
        old_pin = coordinate(old_address) if isinstance(old_address, dict) else None
        new_pin = coordinate(new_address) if isinstance(new_address, dict) else None
        csv_pin = [float(saved['kinh_do']), float(saved['vi_do'])] if saved and saved['kinh_do'] and saved['vi_do'] else None
        if pin:
            coordinate_groups[tuple(pin)].append(meta['tin_id'])
        labels = []
        for dt in soup.select('dt'):
            if 'Diện tích' in dt.get_text(strip=True):
                dd = dt.find_next_sibling('dd')
                if dd:
                    labels.append(dict(label=dt.get_text(strip=True), value=dd.get_text()))
        audit = dict(tin_id=meta['tin_id'], included_in_csv=bool(saved), exclusion_reason=reason,
                     html_sha256_matches_manifest=True, source_coordinate_present=bool(pin),
                     csv_coordinate_present=bool(csv_pin), csv_matches_pLocation=(csv_pin == pin) if saved and pin else '',
                     csv_kinh_do=csv_pin[0] if csv_pin else '', csv_vi_do=csv_pin[1] if csv_pin else '',
                     pLocation_kinh_do=pin[0] if pin else '', pLocation_vi_do=pin[1] if pin else '',
                     old_address_has_coordinates=bool(old_pin), new_address_has_coordinates=bool(new_pin),
                     source_old_pin_distance_m=round(distance(pin, old_pin), 6) if pin and old_pin else '',
                     source_new_pin_distance_m=round(distance(pin, new_pin), 6) if pin and new_pin else '',
                     csv_replay_differing_fields=';'.join(differing), old_district=old_address.get('district') if isinstance(old_address, dict) else '',
                     embedded_pType=obj.get('pType'), embedded_pTypeLvl0=obj.get('pTypeLvl0'),
                     pArea=obj.get('pArea'), pLandArea=obj.get('pLandArea'), pGrossFloorArea=obj.get('pGrossFloorArea'),
                     csv_dien_tich_goc=saved.get('dien_tich_goc', '') if saved else '',
                     csv_dien_tich_m2=saved.get('dien_tich_m2', '') if saved else '',
                     has_description=isinstance(obj.get('description'), str),
                     has_aiDescription=isinstance(obj.get('aiDescription'), str),
                     has_generatedSummaryV2=obj.get('generatedSummaryV2') is not None,
                     capture_at=meta['thoi_diem_crawl'], html_path=meta['html_path'])
        audit_rows.append(audit)
        if meta['tin_id'] in case_ids:
            source_keys = ['pLocation', 'pArea', 'pLandArea', 'pGrossFloorArea', 'pNumberOfBedrooms', 'pNumberOfBathrooms', 'pType', 'pSubType', 'pTypeLvl0', 'pTypeLvl1',
                           'type', 'status', 'listingStatus', 'crawledListingStatus', 'verificationStatus', 'posterVerified', 'publicAddress',
                           'sourceType', '_sourceApp', '_publishedAt', '_firstPublishedAt', '_expiredAt', 'shortId']
            fields = {key: obj.get(key) for key in source_keys}
            fields['pAddress'] = safe_address(old_address)
            fields['newPropertyAddress'] = safe_address(new_address)
            fields['display_h1'] = soup.find('h1').get_text() if soup.find('h1') else None
            fields['display_address'] = parsed['dia_chi_goc']
            fields['area_dt_dd'] = labels
            fields['descriptive_fields_present'] = [key for key in ['description', 'manualDescription', 'aiDescription', 'generatedSummaryV2'] if obj.get(key)]
            for key in ['@page', '@newAddressPage']:
                if isinstance(obj.get(key), dict):
                    fields[key] = {k: obj[key].get(k) for k in ['_id', 'slug']}
            case = dict(tin_id=meta['tin_id'], csv_data_row=row_numbers.get(meta['tin_id']),
                        user_feedback=feedback_by_id.get(meta['tin_id']), capture=meta,
                        csv_record=saved, replay_record=parsed, source_fields=fields,
                        description_excerpts=excerpts(obj), checks=audit,
                        same_id_object_variants=[dict(number_of_fields=len(o),
                            pLocation=o.get('pLocation') if isinstance(o.get('pLocation'), (str, dict)) else None,
                            pAddress_coordinates=o['pAddress'].get('coordinates') if isinstance(o.get('pAddress'), dict) else o.get('pAddress')) for o in objects])
            case_records.append(case)
            make_case_file(case)
        if (index+1) % 25 == 0:
            print(f'Đã đối chiếu offline {index+1}/297 HTML.', flush=True)
    csv_write(DEST / 'evidence/all_297_offline_audit.csv', audit_rows, list(audit_rows[0]))
    csv_write(DEST / 'evidence/replay_mismatches.csv', mismatch_fields, ['tin_id', 'field', 'csv_value', 'replay_value'])
    json_write(DEST / 'evidence/cases_17.json', case_records)
    groups = [dict(coordinates=list(pin), tin_ids=identifiers, count=len(identifiers))
              for pin, identifiers in coordinate_groups.items() if len(identifiers) > 1]
    json_write(DEST / 'evidence/repeated_source_coordinates.json', groups)
    included_audit = [r for r in audit_rows if r['included_in_csv']]
    summary = dict(created_at=datetime.now(TZ).isoformat(), network_disabled=True,
        detail_html_audited=len(audit_rows), included_csv=len(listings), excluded=len(excluded),
        user_feedback_cases=len(FEEDBACK), user_numeric_coordinate_reports=8,
        user_unverified_coordinate_reports=1, user_unavailable_listing_reports=3, user_area_reports=1,
        user_reference_coordinates_supplied=False, independent_ground_truth_checked=False,
        source_coordinate_present_all=sum(r['source_coordinate_present'] for r in audit_rows),
        csv_coordinate_present=sum(r['csv_coordinate_present'] for r in included_audit),
        csv_matches_source_coordinate=sum(r['csv_matches_pLocation'] is True for r in included_audit),
        csv_coordinate_differs_from_source=sum(r['csv_matches_pLocation'] is False for r in included_audit),
        csv_replay_mismatched_fields=len(mismatch_fields),
        source_old_coordinates_nonzero_distance=sum(isinstance(r['source_old_pin_distance_m'], (int,float)) and r['source_old_pin_distance_m'] > 0 for r in audit_rows),
        source_new_coordinates_nonzero_distance=sum(isinstance(r['source_new_pin_distance_m'], (int,float)) and r['source_new_pin_distance_m'] > 0 for r in audit_rows),
        repeated_coordinate_groups=len(groups), repeated_coordinate_listings=sum(g['count'] for g in groups),
        same_coordinates_are_not_independent_confirmation=True,
        included_pArea_missing_or_zero=sum(r['pArea'] in (None,0) for r in included_audit),
        included_multiple_positive_area_fields=sum(sum(isinstance(r[k],(int,float)) and r[k]>0 for k in ['pArea','pLandArea','pGrossFloorArea'])>1 for r in included_audit),
        included_missing_exported_area=sum(not r['csv_dien_tich_m2'] for r in included_audit),
        case_ids=sorted(case_ids),
        request_count_before=json.loads((ROOT/'pilot/data/run_state.json').read_text(encoding='utf-8'))['request_count'])
    json_write(DEST / 'evidence/audit_summary.json', summary)
    paths = ['BRIEF_giai_doan_1.md','KE_HOACH_GIAI_DOAN_1.md','README.md','NOTES.md','main.py','requirements.txt',
             'pilot/data/listings.csv','pilot/data/manifest.jsonl','pilot/data/run_state.json','pilot/logs/requests.csv','reports/environment.json']
    paths += [p.relative_to(ROOT).as_posix() for directory in ['src','tests','pilot/reports','pilot/outputs'] for p in (ROOT/directory).iterdir() if p.is_file() and p.suffix in ['.py','.md','.csv','.json','.jsonl','.png']]
    for relative in paths:
        dest = DEST / 'snapshot' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, dest)
    json_write(DEST / 'evidence/source_capture_manifest_17.json', [m for m in manifest if m.get('tin_id') in case_ids])
    after = {path: sha(ROOT/path) for path in protected}
    assert before == after, 'Tệp pilot hoặc mã nguồn đã thay đổi ngoài phạm vi bàn giao.'
    json_write(DEST / 'evidence/preservation_check.json', dict(before=before, after=after, identical=True,
        raw_html_hash_verified=len(audit_rows), request_count_after=json.loads((ROOT/'pilot/data/run_state.json').read_text(encoding='utf-8'))['request_count']))
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    run()
