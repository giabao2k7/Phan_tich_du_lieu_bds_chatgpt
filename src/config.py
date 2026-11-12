from pathlib import Path
from datetime import timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=7))
AGENT = 'MosoResearch/1.0'
SOURCES = {
    'can_ho': 'https://moso.vn/ban-can-ho-chung-cu-thanh-pho-ho-chi-minh',
    'nha_hem': 'https://moso.vn/ban-nha-hem-thanh-pho-ho-chi-minh-bff6mn',
    'nha_mat_tien': 'https://moso.vn/ban-nha-mat-tien-thanh-pho-ho-chi-minh',
}
COLUMNS = ['tin_id', 'url', 'thoi_diem_crawl', 'html_path', 'loai_hinh',
           'nhom_loai_hinh', 'gia_goc', 'gia_vnd', 'gia_m2_goc', 'gia_m2_vnd',
           'gia_m2_tinh_vnd', 'dien_tich_goc', 'dien_tich_m2', 'loai_dien_tich',
           'quan_phuong_goc', 'dia_chi_goc', 'quan_huyen_chuan', 'vi_do', 'kinh_do',
           'so_phong_ngu', 'so_phong_ve_sinh', 'ngay_dang_goc', 'ngay_dang']
DISTRICTS = [f'Quận {i}' for i in range(1, 13)] + ['Bình Thạnh', 'Bình Tân',
    'Gò Vấp', 'Phú Nhuận', 'Tân Bình', 'Tân Phú', 'Thủ Đức', 'Bình Chánh',
    'Cần Giờ', 'Củ Chi', 'Hóc Môn', 'Nhà Bè']
