"""Đóng gói hồ sơ đã kiểm tra; không gọi mạng và không đổi nguồn pilot."""
import csv
import hashlib
import json
import shutil
import socket
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, TZ

BASE = ROOT / 'handoff'
DOCS = BASE / '2026-11-02_review'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blocked(*args, **kwargs):
    raise RuntimeError('Không dùng mạng khi đóng gói hồ sơ.')


def check_archive(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, 'ZIP lỗi CRC: ' + str(path)
        names = archive.namelist()
        assert len(names) == len(set(names)), 'ZIP trùng đường dẫn'
        assert not any(name.startswith('/') or '..' in Path(name).parts for name in names)
        return len(names)


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    socket.socket = blocked
    socket.create_connection = blocked
    summary = json.loads((DOCS/'evidence/audit_summary.json').read_text(encoding='utf-8'))
    preserved = json.loads((DOCS/'evidence/preservation_check.json').read_text(encoding='utf-8'))
    assert summary['detail_html_audited'] == 297
    assert preserved['identical'] and preserved['request_count_after'] == 313
    assert summary['csv_replay_mismatched_fields'] == 0
    for relative, expected in preserved['after'].items():
        assert digest(ROOT/relative) == expected, relative
    for name in ['build_review_dossier.py', 'package_review_dossier.py', 'add_coordinate_conflict_evidence.py']:
        target = DOCS/'snapshot/scripts'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/'scripts'/name, target)
    lines = ['# Kết quả đối chiếu offline định lượng', '',
        f'Lập hồ sơ: {summary["created_at"]}. Chặn socket, không tra bản đồ hoặc website.', '',
        '| Phép kiểm tra | Kết quả | Diễn giải đúng phạm vi |', '|---|---:|---|',
        f'| HTML chi tiết khớp SHA-256 manifest | {summary["detail_html_audited"]}/297 | Tệp nguồn lưu không thay đổi |',
        f'| Dòng CSV | {summary["included_csv"]} | Theo bộ lọc cũ, chưa xác nhận địa lý thực tế |',
        f'| Tin bị loại trước đây | {summary["excluded"]} | Không tự loại thêm trong lần bàn giao |',
        f'| Dòng CSV có tọa độ | {summary["csv_coordinate_present"]}/295 | Có số không đồng nghĩa tọa độ thật chính xác |',
        f'| Cặp CSV khớp pLocation | {summary["csv_matches_source_coordinate"]} | Chỉ xác nhận phép chép tọa độ nguồn |',
        f'| Cặp CSV khác pLocation có sẵn | {summary["csv_coordinate_differs_from_source"]} | Không tìm thấy sai khác kiểu này trong lần kiểm tra |',
        f'| Số trường CSV khác chạy lại parser | {summary["csv_replay_mismatched_fields"]} | Parser cùng logic, không phải kiểm định độc lập ngữ nghĩa |',
        f'| pLocation khác tọa độ địa chỉ cũ, khi có hai cặp số | {summary["source_old_coordinates_nonzero_distance"]} | So hai trường cùng HTML, không có tọa độ thật |',
        f'| pLocation khác tọa độ địa chỉ mới, khi có hai cặp số | {summary["source_new_coordinates_nonzero_distance"]} | Như trên |',
        f'| Nhóm có nhiều ID trùng chính xác tọa độ nguồn | {summary["repeated_coordinate_groups"]} | Có thể cùng địa điểm; không mặc định là sai hoặc trùng tin |',
        f'| Tin thuộc các nhóm tọa độ trùng | {summary["repeated_coordinate_listings"]} | Không suy nguyên nhân từ trùng cặp số |',
        f'| Tin giữ có pArea thiếu hoặc bằng 0 | {summary["included_pArea_missing_or_zero"]} | Nguồn còn các trường diện tích khác |',
        f'| Tin giữ có hơn một trường diện tích nhúng dương | {summary["included_multiple_positive_area_fields"]} | Không khẳng định các trường cùng nghĩa hoặc đáng lẽ bằng nhau |',
        f'| Tin giữ thiếu diện tích xuất CSV | {summary["included_missing_exported_area"]} | Có ca 168 cần xem bằng chứng loại diện tích |',
        '| Sai số địa lý được agent xác minh độc lập | 0 | Không có điểm đối chứng và không dùng nguồn ngoài |',
        '| Request mới trong lần nghiên cứu | 0 | run_state và log giữ nguyên 313 |', '',
        '## Phản hồi người dùng và giới hạn', '',
        '8 ca có khoảng lệch người dùng báo, 1 ca tọa độ không xác minh được, 1 ca diện tích, 3 ca tin không còn xem được. Tổng 13 ID.',
        'Các nhóm này là cách phân loại bảng phản hồi, không phải các kết luận sai đã được xác nhận.', '',
        'Chi tiết từng phép kiểm tra: evidence/all_297_offline_audit.csv; hồ sơ 17 ca: evidence/cases_17.json.',
        'Không có khuyến nghị giữ/loại, sửa tọa độ hoặc cách chọn diện tích trong tài liệu này.', '']
    (DOCS/'05_KET_QUA_DOI_CHIEU.md').write_text('\n'.join(lines), encoding='utf-8')
    cases = json.loads((DOCS/'evidence/cases_17.json').read_text(encoding='utf-8'))
    extra_cases = json.loads((DOCS/'evidence/additional_coordinate_conflicts_3.json').read_text(encoding='utf-8'))
    from scripts.build_review_dossier import make_case_file
    for case in cases + extra_cases:
        make_case_file(case)
    matrix = []
    for case in cases:
        feedback = case.get('user_feedback')
        if not feedback:
            continue
        saved = case['csv_record']
        fields = case['source_fields']
        pin = fields.get('pLocation', {}).get('coordinates', [])
        matrix.append(dict(tin_id=case['tin_id'], user_stt=feedback['user_stt'], csv_data_row=case['csv_data_row'],
            user_field=feedback['field'], user_note=feedback['note'], user_reported_distance_m=feedback['reported_distance_m'],
            csv_kinh_do=saved['kinh_do'], csv_vi_do=saved['vi_do'], source_pLocation_json=json.dumps(pin),
            csv_matches_pLocation=case['checks']['csv_matches_pLocation'], csv_dien_tich_goc=saved['dien_tich_goc'],
            csv_dien_tich_m2=saved['dien_tich_m2'], embedded_pLandArea=fields.get('pLandArea'),
            old_district=fields.get('pAddress', {}).get('district'), capture_at=case['capture']['thoi_diem_crawl'],
            capture_http_status=case['capture']['status_code'], real_world_location_independently_verified=False,
            case_file=f'evidence/cases/{case["tin_id"]}.md'))
    matrix.sort(key=lambda row: row['user_stt'])
    with (DOCS/'evidence/feedback_vs_source.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(matrix[0]))
        writer.writeheader()
        writer.writerows(matrix)
    with (DOCS/'FILE_INDEX.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['path', 'bytes', 'sha256'])
        for path in sorted(DOCS.rglob('*')):
            if path.is_file() and path.name != 'FILE_INDEX.csv':
                writer.writerow([path.relative_to(DOCS).as_posix(), path.stat().st_size, digest(path)])
    primary = BASE/'HO_SO_DANH_GIA_MOSO.zip'
    with zipfile.ZipFile(primary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(DOCS.rglob('*')):
            if path.is_file():
                archive.write(path, (Path(DOCS.name)/path.relative_to(DOCS)).as_posix())
    manifest = [json.loads(line) for line in (ROOT/'pilot/data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    selected = set(summary['case_ids']) | {case['tin_id'] for case in extra_cases}
    source_note = ('# HTML nguồn gốc đã lưu\n\n'
        'Đây là HTML website trả về trong pilot trước đây, không tải mới. Có thể chứa thông tin liên hệ; '
        'không chỉnh sửa hoặc loại thông tin khỏi bản nguồn. Gói này được chuẩn bị riêng trên máy, chưa gửi đi.\n\n'
        'Giải nén dưới snapshot/ của gói hồ sơ nếu cần ghép thành bản repo offline; các đường dẫn pilot/... '
        'trùng với html_path trong manifest. Mỗi HTML có SHA-256 trong manifest. '
        'Chỉ đánh giá hồ sơ; chưa được ủy quyền chạy crawler hoặc sửa dữ liệu.\n')
    archives = [primary]
    for filename, subset in [('HTML_GOC_20_TIN.zip', [m for m in manifest if m.get('tin_id') in selected]),
                             ('HTML_TOAN_BO_PILOT.zip', manifest)]:
        path = BASE/filename
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr('README_HTML.md', source_note)
            for meta in subset:
                source = ROOT/meta['html_path']
                assert digest(source) == meta['sha256'], meta['html_path']
                archive.write(source, meta['html_path'])
            if filename == 'HTML_GOC_20_TIN.zip':
                archive.writestr('SOURCE_MANIFEST_20.json', json.dumps(subset, ensure_ascii=False, indent=2))
            else:
                for relative in ['pilot/data/manifest.jsonl', 'pilot/data/run_state.json', 'pilot/logs/requests.csv']:
                    archive.write(ROOT/relative, relative)
        archives.append(path)
    package_manifest = dict(created_at=datetime.now(TZ).isoformat(), request_count=313,
                            source_files_unchanged=True, packages=[])
    for path in archives:
        files = check_archive(path)
        package_manifest['packages'].append(dict(file=path.name, bytes=path.stat().st_size, sha256=digest(path), files=files))
    for relative, expected in preserved['after'].items():
        assert digest(ROOT/relative) == expected, relative
    (BASE/'PACKAGE_SHA256.json').write_text(json.dumps(package_manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(package_manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
