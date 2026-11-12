import json
import socket
import unittest
from pathlib import Path
from unittest.mock import patch
from src.config import ROOT
from src.parser import parse_detail, list_entries


class SavedHtmlTest(unittest.TestCase):
    def test_streamed_list_keeps_all_twenty_in_order(self):
        path = ROOT / 'pilot/data/list_html/c00abc7dfb4d474ca8879610_2.html'
        self.assertTrue(path.exists(), 'Cần kho nguồn pilot thật để chạy hồi quy.')
        entries, next_url = list_entries(path.read_bytes(), 'https://moso.vn/')
        self.assertEqual(len(entries), 20)
        self.assertEqual(entries[0][0], '6ae798b72cdb82e3b72068cc')
        self.assertEqual(entries[1][0], '6ae76a572cdb82e3b7141af4')
        self.assertTrue(next_url.endswith('?trang=2'))

    def test_utf8_flight_text_and_current_price_regressions(self):
        manifest = [json.loads(line) for line in (ROOT / 'pilot/data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
        by_id = {m['tin_id']: m for m in manifest if m['kind'] == 'detail'}
        with patch.object(socket, 'socket', side_effect=AssertionError('Không được gọi mạng khi parse')):
            meta = by_id['6ae76a572cdb82e3b7141af4']
            first = parse_detail((ROOT / meta['html_path']).read_bytes(), meta)
            second = parse_detail((ROOT / meta['html_path']).read_bytes(), meta)
            self.assertEqual(first, second)
            self.assertEqual(first[0]['quan_huyen_chuan'], 'Nhà Bè')
            meta = by_id['6ae798b72cdb82e3b72068cc']
            row, reason, evidence = parse_detail((ROOT / meta['html_path']).read_bytes(), meta)
            self.assertEqual(reason, '')
            self.assertEqual(row['gia_goc'], '4,25 tỷ')
            self.assertEqual(row['gia_vnd'], 4_250_000_000)
            self.assertEqual(row['quan_huyen_chuan'], 'Thủ Đức')

    def test_frontage_without_visible_type_label(self):
        manifest = [json.loads(line) for line in (ROOT / 'pilot/data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
        meta = next(m for m in manifest if m.get('tin_id') == '6ae7ff012cdb82e3b72bc8b0' and m['kind'] == 'detail')
        row, reason, evidence = parse_detail((ROOT / meta['html_path']).read_bytes(), meta)
        self.assertEqual(evidence['type_label'], '')
        self.assertEqual(evidence['embedded_type'], 'frontage')
        self.assertEqual(row['loai_hinh'], 'nha_mat_tien')
        self.assertEqual(row['gia_vnd'], 340_000_000_000)
        self.assertEqual(row['dien_tich_m2'], 677)
        self.assertEqual(reason, '')
