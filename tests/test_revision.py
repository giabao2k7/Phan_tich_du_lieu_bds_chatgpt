"""Kỳ vọng đọc tay từ hồ sơ độc lập, không dùng cleaner làm oracle."""
import json
import math
import socket
import unittest
from unittest.mock import patch
from src.config import ROOT
from src.parser import parse_detail, soup_from_html, detail_context
from src.cleaner import money, posting_date
from src.observations import valid_coordinates


class RevisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = {m['tin_id']: m for line in (ROOT/'pilot/data/manifest.jsonl').read_text(encoding='utf-8').splitlines() if (m := json.loads(line)).get('kind')=='detail'}

    def parse(self, tid):
        meta = self.manifest[tid]
        with patch.object(socket, 'socket', side_effect=AssertionError('offline')):
            return parse_detail((ROOT/meta['html_path']).read_bytes(), meta)

    def test_specific_area_labels_and_source_container(self):
        for tid, value in [('6ae76a572cdb82e3b7141af4',75), ('6ae45114bfaa4b4f2be2e31d',74), ('6ae2b887575dffe7bf6cef1e',52), ('6ae2aafdfaae27449455b5de',43.60)]:
            with self.subTest(tid=tid):
                row,_,e = self.parse(tid)
                self.assertEqual(row['loai_dien_tich'], 'tim tường')
                self.assertEqual(row['dien_tich_m2'],value)
                self.assertTrue(any(o['quantity']=='Diện tích tim tường' and o['locator'].startswith('#property-features') for o in e['observations']))

    def test_land_is_not_apartment_area(self):
        for tid, value in [('6ae29887faae274494541131',168),('6adb14293a2a4dbcf2933030',104)]:
            row,_,e = self.parse(tid)
            self.assertIsNone(row['dien_tich_m2'])
            self.assertEqual(row['gia_m2_tinh_vnd'],'')
            self.assertEqual(e['asset_unit_status'],'unresolved')
            self.assertFalse(e['semantic_eligible'])
            self.assertTrue(any(o['quantity']=='pLandArea' and o['raw_value']==value for o in e['observations']))
        self.assertIn('DTCN: 168m',self.parse('6ae29887faae274494541131')[2]['description_excerpts'])

    def test_opal_candidate_conflict_does_not_move_source(self):
        row,_,e = self.parse('6ad98e4c63be9ff37837ab2e')
        self.assertEqual(e['scope_status'],'conflicted')
        self.assertEqual([row['kinh_do'],row['vi_do']],[106.72641,10.877589])
        self.assertIn('Kha Vạn Cân',row['dia_chi_goc'])
        self.assertTrue(any('Opal Boulevard' in x for x in e['description_excerpts']))

    def test_parallel_area_quantities(self):
        for tid, land, usable in [('6ae7fa572cdb82e3b72b4f4a',37.24,74.48),('6ae45f37bfaa4b4f2be3ebdc',96.5,118.9)]:
            _,_,e = self.parse(tid)
            values = {a['area_type']:a['area_m2'] for a in e['analytical_areas']}
            self.assertEqual(values['đất công nhận'],land)
            self.assertEqual(values['sử dụng'],usable)

    def test_internal_coordinate_distances(self):
        for tid, expected in [('6a55eb7444e3cc553294e653',.026261),('6a78500cef49c1cf412aa06e',3580.314698),('6ae442d5bfaa4b4f2be1b47e',350.499435)]:
            _,_,e = self.parse(tid)
            self.assertAlmostEqual(max(c['distance_m'] for c in e['coordinate_comparisons']),expected,delta=.001)
        self.assertEqual(self.parse('6a55eb7444e3cc553294e653')[2]['scope_status'],'supported_by_source')

    def test_missing_district_is_unresolved(self):
        self.assertEqual(self.parse('6a828ba04d7b7c7731016d92')[2]['scope_status'],'out_by_source')
        self.assertEqual(self.parse('6a7d636bcda0c4ce3027c9c3')[2]['scope_status'],'unresolved')

    def test_unavailable_reports_do_not_change_snapshot(self):
        for tid in ['6ae7f74f2cdb82e3b72b05c2','6ae7f05b2cdb82e3b72a2b18','6ae7e20e2cdb82e3b728b048']:
            _,_,e = self.parse(tid)
            self.assertEqual(e['snapshot']['html_sha256'],self.manifest[tid]['sha256'])
            self.assertEqual(e['snapshot']['capture_at'],self.manifest[tid]['thoi_diem_crawl'])
            self.assertEqual(e['availability_status'],'current_unknown')

    def test_price_disagreements_remain(self):
        for tid, price, display, expected in [('6abf1c38a3b5530d263a95c1',15000000000,253420000,203970628.229535),('6ae45f37bfaa4b4f2be3ebdc',14000000000,112000000,145077720.207254)]:
            row,_,_=self.parse(tid)
            self.assertEqual(row['gia_vnd'],price)
            self.assertEqual(row['gia_m2_vnd'],display)
            self.assertAlmostEqual(float(row['gia_m2_tinh_vnd']),expected,places=4)

    def test_strict_money_independent_examples(self):
        for text, expected in [('4,25 tỷ',4250000000),('3.05 tỷ',3050000000),('~55,37 triệu/m²',55370000),('340 tỷ',340000000000),('1 tỷ 200 triệu',None),('1.980 VNĐ',None),('Thỏa thuận',None),('2,5-3 tỷ',None)]:
            self.assertEqual(money(text),expected,text)
        self.assertEqual(posting_date('2 giờ trước','2026-11-01T17:30:00+00:00'),'2026-11-01')
        self.assertEqual(posting_date('hôm nay','2026-11-01T18:30:00+00:00','2025-01-01T00:00:00Z'),'2026-11-02')

    def test_invalid_coordinate_values(self):
        for value in [[True,10],[106,float('nan')],[float('inf'),10],[181,10],[106,91],[10],None]:
            self.assertFalse(valid_coordinates(value))

    def test_recommendation_cannot_supply_main_fields(self):
        tid = '6ae76a572cdb82e3b7141af4'
        meta = self.manifest[tid]
        html = (ROOT/meta['html_path']).read_bytes()
        soup = soup_from_html(html)
        extra = soup.new_tag('article')
        extra.append(soup_from_html('<dl><dt>Diện tích thông thủy</dt><dd>999m²</dd></dl>'))
        soup.body.append(extra)
        self.assertEqual(parse_detail(str(soup),meta)[0]['dien_tich_m2'],75)

    def test_conflicting_same_id_is_an_explicit_error(self):
        records = '1:'+json.dumps({'_id':'example','type':'sale','pArea':75})+'\n2:'+json.dumps({'_id':'example','type':'sale','pArea':76})+'\n'
        payload = json.dumps([1,records])
        html = '<h1>Main</h1><dl id="property-features"></dl><script>self.__next_f.push('+payload+')</script>'
        with self.assertRaisesRegex(ValueError,'Xung đột đối tượng'):
            detail_context(soup_from_html(html),'example')

    def test_same_quantity_conflict_retains_both_candidates(self):
        tid = '6ae76a572cdb82e3b7141af4'
        meta = self.manifest[tid]
        soup = soup_from_html((ROOT/meta['html_path']).read_bytes())
        duplicate = soup_from_html('<div><dt>Diện tích tim tường</dt><dd>76m²</dd></div>').find('div')
        soup.select_one('#property-features').append(duplicate)
        row,_,e = parse_detail(str(soup),meta)
        self.assertIsNone(row['dien_tich_m2'])
        self.assertEqual(e['internal_consistency'],'conflicted')
        self.assertEqual([o['raw_value']for o in e['observations']if o['quantity']=='Diện tích tim tường'],['75m²','76m²'])
        self.assertFalse(any(a['area_type']=='tim tường'for a in e['analytical_areas']))


if __name__ == '__main__':
    unittest.main()
