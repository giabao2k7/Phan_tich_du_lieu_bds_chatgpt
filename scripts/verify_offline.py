"""Điểm vào tương thích; v2 so hai replay mới, không so bằng CSV quy tắc cũ."""
from verify_revision import verify, ROOT

if __name__ == '__main__':
    verify(ROOT/'revisions/2026-11-02_offline_v2')
