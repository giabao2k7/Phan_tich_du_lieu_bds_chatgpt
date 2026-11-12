"""Báo cáo v2 cần quan sát/decisions; gọi qua pipeline.parse_saved."""
from .revision_reports import report_revision


def report_quality(rows, excluded, errors, base, crawl_base, *, evidence=None):
    if evidence is None:
        raise ValueError('Nghiệm thu v2 cần evidence; dùng pipeline.parse_saved để bảo đảm truy nguyên.')
    return report_revision(rows, excluded, errors, evidence, base, crawl_base / 'data/manifest.jsonl')
