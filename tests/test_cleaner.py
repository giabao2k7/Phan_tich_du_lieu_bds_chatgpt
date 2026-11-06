import unittest
from src.cleaner import money, area, district, posting_date


class CleanerTest(unittest.TestCase):
    def test_unit_scaling(self):
        self.assertEqual(money('4,25 tỷ'), 4_250_000_000)
        self.assertEqual(money('~55,37 triệu/m²'), 55_370_000)
        self.assertEqual(money('3.05 tỷ'), 3_050_000_000)
        self.assertIsNone(money('Thỏa thuận'))
        self.assertIsNone(money(''))

    def test_relative_date_uses_download_timezone(self):
        self.assertEqual(posting_date('2 giờ trước', '2026-11-02T00:30:00+07:00'), '2026-11-01')
        self.assertEqual(posting_date('1 tuần trước', '2026-11-02T10:30:00+07:00'), '2026-10-26')
        self.assertEqual(posting_date('1 tháng trước', '2026-11-02T10:30:00+07:00'), '')
        self.assertEqual(posting_date('1 tháng trước', '2026-11-02T10:30:00+07:00', '2026-09-19T22:00:00Z'), '2026-09-20')

    def test_no_district_inference(self):
        self.assertEqual(district('Thành phố Thủ Đức'), 'Thủ Đức')
        self.assertEqual(district('Quận 9'), 'Quận 9')
        self.assertEqual(district('Phường Bình Trưng Đông (Quận 2 cũ)'), '')
        self.assertEqual(district('Thành phố Dĩ An'), '')
        self.assertEqual(area('55.08 m²'), 55.08)
        self.assertIsNone(area(''))
