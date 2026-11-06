"""Đối chiếu mẫu với nút DOM nguồn và lập bảng review; không truy cập mạng."""
import csv
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, SOURCES
from src.parser import soup_from_html


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    base = ROOT / 'pilot'
    with (base / 'data/listings.csv').open(encoding='utf-8-sig', newline='') as file:
        rows = list(csv.DictReader(file))
    selected = []
    for kind in SOURCES:
        selected.extend([row for row in rows if row['loai_hinh'] == kind][:5])
    for condition in [lambda r: not r['gia_m2_goc'], lambda r: not r['dien_tich_goc'],
                      lambda r: not r['so_phong_ngu'], lambda r: r['quan_huyen_chuan'] == 'Quận 2']:
        candidate = next((row for row in rows if condition(row) and row not in selected), None)
        if candidate:
            selected.append(candidate)
    with (base / 'reports/quality_flags.csv').open(encoding='utf-8-sig', newline='') as file:
        flagged_ids = {r['tin_id'] for r in csv.DictReader(file) if r['issue'] == 'Chênh lệch >10%'}
    selected.extend(row for row in rows if row['tin_id'] in flagged_ids and row not in selected)
    lines = ['# Đối chiếu mẫu pilot với HTML đã lưu', '',
             'Kiểm tra tự động các nút DOM cho từng tin, kèm bảng để người dùng đối chiếu độc lập.',
             'Giá ở dt Mức giá/dd/span đầu; diện tích ở dt tương ứng; address cạnh h1; ngày ở time cạnh h1.',
             'Không phải đối chiếu lại trang trực tuyến; không phát sinh request.', '',
             '| ID | Loại | Giá nguồn | Diện tích nguồn | Quận | Kết quả | HTML |',
             '|---|---|---|---|---|---|---|']
    for row in selected:
        soup = soup_from_html((ROOT / row['html_path']).read_bytes())
        heading = soup.find('h1')
        price_term = next(t for t in soup.select('dt') if t.get_text(strip=True) == 'Mức giá')
        price_node = price_term.find_next_sibling('dd').find('span')
        assert price_node.get_text() == row['gia_goc'], row['tin_id'] + ': giá gốc'
        match = re.fullmatch(r'([\d,]+) tỷ', row['gia_goc'])
        if match:
            expected = int(Decimal(match[1].replace(',', '.')) * 10**9)
            assert expected == int(row['gia_vnd']), row['tin_id'] + ': tỷ sang VND'
        assert heading.parent.find('address').get_text() == row['dia_chi_goc'], row['tin_id'] + ': địa chỉ'
        assert heading.parent.find('time').get_text() == row['ngay_dang_goc'], row['tin_id'] + ': ngày gốc'
        source_values = [t.find_next_sibling('dd').get_text() for t in soup.select('dt')
                         if t.get_text(strip=True).startswith('Diện tích') and t.find_next_sibling('dd')]
        if row['dien_tich_goc']:
            assert row['dien_tich_goc'] in source_values, row['tin_id'] + ': diện tích'
        def cell(value):
            return value.replace('|', '\\|').replace('\n', '<br>') or '(thiếu)'
        lines.append('| ' + ' | '.join(map(cell, [row['tin_id'], row['loai_hinh'], row['gia_goc'], row['dien_tich_goc'],
                     row['quan_huyen_chuan'], 'Đạt các kiểm tra DOM nêu trên', row['html_path']])) + ' |')
    lines += ['', f'Tổng mẫu: {len(selected)}. Các quận, tọa độ và loại hình được truy xuất trong field_evidence.jsonl;',
              'cần người dùng đánh giá độc lập với HTML và trang gốc. Không coi kiểm tra DOM là nghiệm thu toàn bộ trường.']
    (base / 'reports/manual_review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Đối chiếu DOM thành công {len(selected)} tin.')


if __name__ == '__main__':
    run()
