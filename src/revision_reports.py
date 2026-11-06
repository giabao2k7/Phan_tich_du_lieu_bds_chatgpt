"""Rapports versionnés hors réseau; chaque contrôle conserve ses limites."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
from .config import COLUMNS, ROOT, SOURCES, DISTRICTS
from .observations import RULE_VERSION


def json_file(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')


def json_lines(path, values):
    path.write_text(''.join(json.dumps(v, ensure_ascii=False, default=str) + '\n' for v in values), encoding='utf-8')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def report_revision(rows, excluded, errors, evidence, base, manifest_path):
    from .pipeline import write_csv
    from .revision_analysis import analyze_revision
    reports = base / 'reports'
    observations = [o for e in evidence for o in e['observations']]
    decisions = [d for e in evidence for d in e['decisions']]
    areas = [a for e in evidence for a in e['analytical_areas']]
    json_lines(reports / 'observations.jsonl', observations)
    json_lines(reports / 'decisions.jsonl', decisions)
    json_lines(reports / 'field_evidence.jsonl', evidence)
    statuses = [dict(e['snapshot'], **{k: e[k] for k in ['extraction_status', 'internal_consistency', 'scope_status', 'asset_unit_status', 'coordinate_verification', 'availability_status', 'semantic_eligible']}) for e in evidence]
    write_csv(reports / 'record_status.csv', statuses, list(statuses[0]) if statuses else ['tin_id'])
    json_lines(base / 'data/analytical_areas.jsonl', areas)
    eligibility = []
    for e in evidence:
        r = e['compatibility_row']
        scope_asset = e['semantic_eligible']
        for purpose, ok, reason in [('price_by_type', scope_asset and bool(r['gia_vnd']) and r['gia_vnd'] > 0, 'requires_sale_scope_asset_positive_price'),
                                    ('district_counts', scope_asset, 'requires_sale_scope_asset'),
                                    ('real_world_distance', False, 'no_external_coordinate_verification')]:
            eligibility.append(dict(tin_id=r['tin_id'], purpose=purpose, eligible=ok, rule=reason))
        for kind in ['thông thủy', 'tim tường', 'đất', 'đất công nhận', 'sử dụng']:
            matches = [a for a in e['analytical_areas'] if a['area_type']==kind and a['eligible']]
            eligibility.append(dict(tin_id=r['tin_id'],purpose='area_' + kind,eligible=bool(matches),rule='requires_source_scope_asset_unique_positive_dom_quantity'))
            eligibility.append(dict(tin_id=r['tin_id'],purpose='price_per_m2_' + kind,eligible=bool(matches) and bool(r['gia_vnd']) and r['gia_vnd']>0,rule='requires_area_eligibility_and_positive_price'))
    write_csv(reports/'eligibility.csv',eligibility,['tin_id','purpose','eligible','rule'])
    coverage = []
    for quantity in sorted({o['quantity'] for o in observations}):
        group = [o for o in observations if o['quantity']==quantity]
        states = Counter(o['value_state'] for o in group)
        coverage.append(dict(quantity=quantity, records_with_observation=len({o['tin_id'] for o in group}),
                             records_total=len(evidence), observed=states['observed'],missing=states['missing'],null=states['null'],
                             zero=states['zero'],reference=states['reference'],unverified='all_source_only'))
    write_csv(reports/'observation_coverage.csv',coverage,list(coverage[0]) if coverage else ['quantity'])
    old_path = manifest_path.parent / 'listings.csv'
    old_rows = read_csv(old_path) if old_path.exists() else []
    old = {r['tin_id']: r for r in old_rows}
    new = {r['tin_id']: r for r in rows}
    evidence_by_id = {e['tin_id']: e for e in evidence}
    diffs = []
    for tid in sorted(old.keys() | new.keys()):
        if tid not in new or tid not in old:
            e = evidence_by_id.get(tid, {})
            diffs.append(dict(tin_id=tid, field='record_membership', before='included' if tid in old else 'excluded', after='included' if tid in new else 'quarantined_or_excluded',
                              source=e.get('snapshot'), reason_code=e.get('scope_status', 'parse_error'), rule_version=RULE_VERSION))
        if tid in old and tid in new:
            for field in COLUMNS:
                before, after = old[tid][field], new[tid][field]
                after_text = '' if after is None else str(after)
                if before == after_text:
                    continue
                # Chênh serialize Decimal vẫn ghi rõ; không tính là thay quan sát nguồn.
                semantic = True
                try:
                    semantic = Decimal(before) != Decimal(after_text)
                except Exception as exc:
                    if not isinstance(exc, (ValueError, ArithmeticError)):
                        raise
                rules = {'dien_tich_goc': 'D4_specific_label_selection', 'dien_tich_m2': 'D4_specific_label_selection',
                         'loai_dien_tich': 'D4_preserve_specific_label', 'gia_m2_tinh_vnd': 'D7_decimal_arithmetic',
                         'gia_vnd': 'D7_strict_money', 'gia_m2_vnd': 'D7_strict_money'}
                diffs.append(dict(tin_id=tid, field=field, before=before, after=after_text,
                                  source=evidence_by_id[tid]['snapshot'], reason_code=rules.get(field, 'D2_scoped_source_extraction'),
                                  rule_version=RULE_VERSION, semantic_change=semantic))
    json_lines(reports / 'field_diff.jsonl', diffs)
    area_audit, flags, queue = [], [], []
    for e in evidence:
        tid = e['snapshot']['tin_id']
        dom = [o for o in e['observations'] if o['quantity'].startswith('Diện tích')]
        specific = [o for o in dom if o['quantity'] != 'Diện tích']
        nums = {o['normalized'] for o in specific if o['normalized'] is not None}
        group = 'multiple_types_same_number' if len(specific) > 1 and len(nums) == 1 else 'multiple_quantities_distinct_numbers' if len(nums) > 1 else 'one_specific' if specific else 'no_specific'
        area_audit.append(dict(tin_id=tid, old_type=old.get(tid, {}).get('loai_dien_tich', ''),
                               old_missing_with_specific=tid in old and not old[tid]['loai_dien_tich'] and bool(specific),
                               group=group, area_decision=e['decisions'][0]['reason_code'],
                               observations=[{'label': o['quantity'], 'raw': o['raw_value'], 'locator': o['locator']} for o in dom]))
        for c in e['coordinate_comparisons']:
            flags.append(dict(tin_id=tid, field='coordinates', issue=c['priority'], value=c['distance_m'], source=c['left'] + ' vs ' + c['right']))
        r = e['compatibility_row']
        if r['gia_m2_vnd'] and r['gia_m2_tinh_vnd']:
            calculated = Decimal(r['gia_m2_tinh_vnd'])
            difference = abs(Decimal(r['gia_m2_vnd'])-calculated)/calculated
            if difference > Decimal('.1'):
                flags.append(dict(tin_id=tid, field='gia_m2', issue='difference_gt_10pct', value=str(difference), source='abs(display-calculated)/calculated; compatibility_area'))
        for col in ['gia_goc', 'gia_m2_goc']:
            normalized = r['gia_vnd' if col == 'gia_goc' else 'gia_m2_vnd']
            if r[col] and normalized is None:
                flags.append(dict(tin_id=tid, field=col, issue='negotiable_or_ambiguous_unparsed', value=r[col], source='DOM/header'))
        if e['scope_status'] != 'supported_by_source' or e['asset_unit_status'] != 'supported_by_source' or e['coordinate_comparisons']:
            queue.append(dict(tin_id=tid, snapshot=e['snapshot'], scope=e['scope_status'], asset_unit=e['asset_unit_status'],
                              internal_consistency=e['internal_consistency'], description_excerpts=e['description_excerpts'], coordinate_comparisons=e['coordinate_comparisons'],
                              competing_claims=['Nguồn cấu trúc/địa chỉ cũ', 'Mô tả hoặc địa chỉ mới/đơn vị tài sản chưa thống nhất'],
                              missing_evidence='Định danh tài sản; nguồn đối chứng có ngày và ranh giới cũ; nếu pin: hệ tọa độ, điểm đại diện, cách đo và độ chính xác; nếu diện tích: tài liệu đại lượng/đơn vị tài sản',
                              adjudication='Chưa phân xử; không tự đổi dữ liệu. Đối chứng ngoài chỉ thu sau ủy quyền riêng.',
                              permitted_use='Quan sát snapshot; phân tích theo eligibility từng mục đích, không khẳng định vị trí thực địa'))
    json_lines(reports / 'area_candidate_audit.jsonl', area_audit)
    json_lines(reports / 'verification_queue.jsonl', queue)
    feedback_path = ROOT / 'handoff/2026-11-02_review/evidence/user_feedback.csv'
    feedback = read_csv(feedback_path) if feedback_path.exists() else []
    # Phản hồi có provenance riêng, không dùng làm tọa độ thật hoặc sửa nguồn.
    json_lines(reports / 'user_feedback.jsonl', [dict(r, status='user_report_not_independently_verified') for r in feedback])
    write_csv(reports / 'quality_flags.csv', flags, ['tin_id', 'field', 'issue', 'value', 'source'])
    chart_checks = analyze_revision(rows, evidence, areas, old_rows, base)
    source_metas = [json.loads(s) for s in manifest_path.read_text(encoding='utf-8').splitlines()]
    detail_metas = [m for m in source_metas if m.get('kind') == 'detail' and m.get('status_code') == 200]
    hashes_ok = all((ROOT/m['html_path']).exists() and hashlib.sha256((ROOT/m['html_path']).read_bytes()).hexdigest() == m['sha256'] for m in source_metas)
    obs_ids = {o['observation_id'] for o in observations}
    decision_links_ok = all(d['candidates'] and set(d['candidates']) <= obs_ids for d in decisions)
    scope_counts = Counter(e['scope_status'] for e in evidence)
    scope_counts['parse_error'] = len(errors)
    state = json.loads((manifest_path.parent / 'run_state.json').read_text(encoding='utf-8'))
    logs = read_csv(manifest_path.parent.parent / 'logs/requests.csv')
    intervals = [(datetime.fromisoformat(b['thoi_diem'])-datetime.fromisoformat(a['thoi_diem'])).total_seconds() for a,b in zip(logs, logs[1:])]
    checks = dict(total_detail=len(detail_metas), parsed=len(evidence), errors=len(errors),
                  conserved_total=len(evidence)+len(errors)==len(detail_metas), scope_counts=dict(scope_counts),
                  csv_rows=len(rows), schema_23=len(COLUMNS)==23 and all(set(r)==set(COLUMNS) for r in rows),
                  unique_ids=len({r['tin_id'] for r in rows})==len(rows), unique_urls=len({r['url'] for r in rows})==len(rows),
                  csv_scope_source_supported=all(evidence_by_id[r['tin_id']]['scope_status']=='supported_by_source' and r['quan_huyen_chuan'] in DISTRICTS for r in rows),
                  all_manifest_hashes_match=hashes_ok, decision_observation_links=decision_links_ok,
                  request_count=len(logs), counter=state['request_count'], minimum_request_start_interval_seconds=min(intervals) if intervals else None,
                  historical_request_controls=len(logs)==state['request_count'] and len(logs)<=state['limit'] and bool(intervals) and min(intervals)>=1.5,
                  recovered_area_candidates=sum(a['old_missing_with_specific'] for a in area_audit),
                  area_groups=dict(Counter(a['group'] for a in area_audit)),
                  semantic_eligible=sum(e['semantic_eligible'] for e in evidence), flags=len(flags), verification_queue=len(queue),
                  analysis_checks=chart_checks, rule_version=RULE_VERSION)
    json_file(reports / 'checks.json', checks)
    lines = ['# Chất lượng bản sửa offline D1–D8', '',
             f"297 HTML là tập pilot lịch sử; lần này xử lý {len(detail_metas)}: {len(evidence)} thành công + {len(errors)} lỗi.",
             f"CSV tương thích: {len(rows)} tin; tách khỏi CSV {len(excluded)}; đủ điều kiện ngữ nghĩa theo nguồn: {checks['semantic_eligible']}.",
             'Không gọi là tài sản duy nhất, giao dịch, vị trí đã xác minh hoặc tồn kho đang bán hiện tại.', '',
             '## Trạng thái phạm vi', '', *[f'- {k}: {v}' for k,v in scope_counts.items()], '',
             f"Ứng viên mất loại diện tích cũ được tái sinh từ DOM tin chính: {checks['recovered_area_candidates']}.",
             f"Nhóm diện tích: {checks['area_groups']}. Các đại lượng khác nghĩa không bị coi là xung đột.",
             'CSV vẫn chia giá/diện tích đã chọn như chỉ số số học tương thích. Chỉ dùng analytical_areas.jsonl cho giá/m² phân tầng.',
             'Diện tích chính: thông thủy cho căn hộ; đất công nhận cho nhà; không bù bằng loại khác.', '',
             '## Thiếu theo cột CSV', '', '| Cột | Thiếu | Mẫu số |', '|---|---:|---:|']
    for col in COLUMNS:
        lines.append(f'| {col} | {sum(r[col] in (None, "") for r in rows)} | {len(rows)} |')
    lines += ['', '## Điều kiện đủ và giới hạn', '',
              '- Giá/địa bàn: sale, scope supported_by_source và asset unit supported_by_source; chặn các ca còn tranh chấp.',
              '- Diện tích/giá trên m²: thêm nhãn DOM cụ thể, số dương, cùng đại lượng không xung đột; thống kê riêng từng loại.',
              '- Không gian/khoảng cách thực địa: chưa đủ điều kiện với mọi pin chưa có đối chứng. ≤1 m chỉ là ưu tiên rà soát thấp.',
              '- Phòng tắm ánh xạ tương thích sang cột vệ sinh, chưa chứng minh số WC. Phường cũ/mới ở observations, không chuẩn hóa.',
              '- Ngày tương đối theo capture +07; datetime fallback có provenance riêng. Nhãn website không là xác nhận thực địa.',
              f"- {len(flags)} cảnh báo; {len(queue)} phiếu cần phân xử; không lấy số cảnh báo làm số tin sai.",
              f"- Request lịch sử {len(logs)}/{state['limit']}; lần sửa offline không gửi request.",
              '- Kiểm socket, bảo toàn nguồn, tái lập hai lần và môi trường được ghi riêng trong verification.json sau khi chạy kiểm chứng.',
              '- Bảng tác động cũ/mới chỉ mô tả thay đổi tập phân tích, không chứng minh độ đúng thực tế.',
              '- IQR theo từng loại hình và đại lượng đủ nghĩa, giữ ngoại lệ; xem outputs/summary_by_type.csv.']
    (reports / 'data_quality.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    acceptance = ['# Nghiệm thu xét lại', '', 'Không nghiệm thu full hoặc xác nhận toàn bộ đúng địa lý.', '',
                  '| Mục BRIEF | Kết quả | Bằng chứng / giới hạn |', '|---|---|---|',
                  '| 1. Môi trường sạch | Chờ kiểm chứng riêng | verification.json; không kế thừa kết quả v1 |',
                  '| 2. Phạm vi và duy nhất | Chưa đạt toàn mục | checks.json kiểm ID/URL/nhãn; còn tranh chấp và chưa có ground truth |',
                  '| 3. Khoảng 2.000 tin | Chưa đạt, chưa chạy full | Chỉ tái xử lý pilot; không request mới |',
                  f"| 4. Schema và ngữ nghĩa | {'Đạt kiểm cấu trúc/truy nguyên, ngữ nghĩa còn giới hạn' if checks['schema_23'] and decision_links_ok else 'Không đạt'} | observations/decisions/field_diff; phân tầng diện tích, không tuyên bố chính xác pháp lý |",
                  f"| 5. HTML, delay, log, PII | {'Đạt hash/log/delay lịch sử; PII chỉ allowlist, chưa audit thủ công toàn bộ' if hashes_ok and checks['historical_request_controls'] else 'Không đạt'} | checks.json; không xuất cả đối tượng nguồn, mô tả chỉ đoạn BĐS |",
                  f"| 6. Thống kê và biểu đồ | {'Đạt kiểm tệp/số liệu; chờ kiểm trực quan' if chart_checks['files_exist'] and chart_checks['counts_match'] else 'Không đạt'} | outputs/chart_checks.json; phải mở PNG và ghi kết quả trong verification.json |"]
    (reports / 'acceptance.md').write_text('\n'.join(acceptance)+'\n', encoding='utf-8')
