"""Chạy bộ test không cần dữ liệu riêng tư; công khai phần không được chọn."""
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Không sửa test gốc hoặc ngụ ý rằng test cần nguồn riêng tư đã đạt.
PRIVATE_TEST_PREFIXES = (
    'test_saved_html.',
    'test_revision.',
    'test_location_review.LocationReviewTest.test_point_is_marker_not_viewport',
    'test_location_review.LocationReviewTest.test_result_coverage_and_independent_distances',
    'test_location_review.LocationReviewTest.test_wrong_house_number_geocoder_result_is_rejected',
    'test_api_probe.ApiProbeTest.test_url_and_real_robots_snapshot',
    'test_api_html_probe.ApiHtmlProbeTest.test_real_saved_html_identity_type_and_known_id',
)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    with patch.object(socket, 'socket', side_effect=AssertionError('Shared tests forbid network')):
        tests = list(flatten(unittest.defaultTestLoader.discover(str(ROOT / 'tests'))))
        selected, private = [], []
        for test in tests:
            target = private if test.id().startswith(PRIVATE_TEST_PREFIXES) else selected
            target.append(test)
        print(f'Bộ chia sẻ: {len(selected)} test; không chọn {len(private)} test cần dữ liệu riêng tư.', flush=True)
        for test in private:
            print(f'  Cần nguồn cục bộ: {test.id()}', flush=True)
        if not selected:
            print('Không tìm thấy test cho bản chia sẻ.', file=sys.stderr)
            return 1
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
