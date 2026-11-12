"""Phân tích v2 chỉ chạy khi có trạng thái và tập diện tích có nhãn."""
from .revision_analysis import analyze_revision


def analyze(rows, base, *, evidence=None, areas=None, old_rows=None):
    if evidence is None or areas is None:
        raise ValueError('Không phân tích diện tích trộn nghĩa; dùng pipeline.parse_saved v2.')
    return analyze_revision(rows, evidence, areas, old_rows or [], base)
