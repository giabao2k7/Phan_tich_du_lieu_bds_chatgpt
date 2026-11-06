# Thu thập và phân tích tin bán moso.vn — giai đoạn 1

Yêu cầu gốc: [BRIEF](BRIEF_giai_doan_1.md). Kế hoạch được lưu nguyên văn tại
[KE_HOACH_GIAI_DOAN_1.md](KE_HOACH_GIAI_DOAN_1.md).

## Môi trường Windows

Python **3.12.11** bản Windows native. Trong PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Máy thực thi có thêm Python MSYS2 cùng phiên bản nhưng không tương thích wheel
Windows. Runtime native được đặt riêng trong `.runtime/python/`. Xem NOTES.md
về bootstrap bằng uv nếu ensurepip bị môi trường hạn chế.

Kho wheel đã xác minh nằm trong `.runtime/wheels/`. Có thể cài offline:

```powershell
python -m venv .venv-verify
.\.venv-verify\Scripts\python.exe -m pip install -r requirements.txt --no-index --find-links .runtime/wheels
.\.venv-verify\Scripts\python.exe scripts/verify_offline.py
```

## Lệnh

```powershell
.\.venv\Scripts\python.exe main.py pilot
.\.venv\Scripts\python.exe -B main.py parse pilot/data/raw_html revisions/2026-11-02_offline_v2/data/listings.csv
# Chỉ chạy dòng dưới sau khi người dùng cho phép full:
.\.venv\Scripts\python.exe main.py full
```

Pilot đã bắt đầu sẽ không được khởi tạo lại. Full cũng chỉ có một lượt; file
`data/run_state.json` là dấu bảo vệ lâu dài, không xóa để chạy lại. Không có retry
hay tùy chọn tăng trần. `scripts/survey.py` và `scripts/continue_pilot.py` ghi lại
việc khảo sát nối tiếp trong pilot phát triển ban đầu; có kiểm tra trạng thái
chính xác, không phải lệnh chạy lại/resume cho người dùng.

`parse` đọc manifest nằm cạnh thư mục raw_html, kiểm tra SHA-256 và metadata;
không dùng mtime, không gọi mạng. Lệnh tạo lại CSV, báo cáo và ba biểu đồ bằng
cùng parser/cleaner dùng khi crawl. Thay đổi phải sửa code rồi parse lại.

## Bản sửa offline ngày 02/11/2026

Người dùng đã yêu cầu triển khai bản đánh giá độc lập; phụ lục hợp đồng
`handoff/HOP_DONG_OFFLINE_V2_2026-11-02.md` áp dụng cho lần sửa này.
Không chạy full. Nguồn `pilot/` và ba ZIP được giữ nguyên.
Không dùng lệnh parse ghi đè CSV lịch sử (pipeline từ chối).

Kết quả mới ở `revisions/2026-11-02_offline_v2/`: CSV tương thích 23 cột;
`reports/observations.jsonl`, `decisions.jsonl`, `record_status.csv`,
`field_diff.jsonl`, `verification_queue.jsonl`; `data/analytical_areas.jsonl`
cho phân tích có nhãn diện tích. `gia_m2_tinh_vnd` trong CSV chỉ là phép chia
tương thích, chưa đủ nghĩa để trộn các loại diện tích.

Chạy kiểm chứng hai lượt offline bằng môi trường mới đã cài dependencies:

```powershell
.\.verification\offline_v2_env\Scripts\python.exe -B scripts/verify_revision.py
```

Lệnh kiểm chứng v2 so hai đầu ra mới theo byte, kiểm hash nguồn/log/counter,
chặn socket và chạy toàn bộ test. `scripts/verify_offline.py` nay trỏ về
kiểm chứng v2; không còn yêu cầu CSV mới giống CSV quy tắc cũ.

## Đầu ra

- `pilot/data/listings.csv`: UTF-8 BOM, đủ 23 cột đúng BRIEF.
- `pilot/data/raw_html/`: HTML chi tiết nguyên bản theo ID đối tượng của tin.
- `pilot/data/list_html/`: robots, trang danh sách và chuyển hướng.
- `pilot/data/manifest.jsonl`: URL, timestamp +07:00, nguồn, thứ tự, hash và đường dẫn từ gốc dự án.
- `pilot/logs/requests.csv`: đúng ba cột URL, thời điểm, mã HTTP.
- `pilot/reports/`: chất lượng, nghiệm thu, bằng chứng trường, loại trừ, lỗi parse, cảnh báo và mẫu đối chiếu.
- `pilot/outputs/`: thống kê theo loại và ba PNG.

Full dùng `data/`, `logs/`, `reports/`, `outputs/` ở gốc. Không xuất thông tin
người đăng/điện thoại. HTML có thể chứa những thông tin đó, do đó không đưa
raw HTML vào git; yêu cầu gỡ từ website phải được thực hiện theo BRIEF.

Thiết kế module: `crawler` kiểm soát mạng; `collection` phân trang/khử trùng;
`parser` giải mã HTML streaming và Flight; `cleaner` chuẩn hóa; `observations`
giữ chứng cứ/quyết định; `pipeline` tái lập offline; `revision_reports` kiểm
tra; `revision_analysis` thống kê/vẽ theo điều kiện đủ. `quality` và `analysis`
là điểm vào tương thích, từ chối chạy thiếu chứng cứ v2.
