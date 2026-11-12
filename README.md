# Thu thập và phân tích tin bán bất động sản moso.vn

Chương trình Python thu thập HTML, trích xuất và chuẩn hóa tin bán căn hộ,
nhà hẻm và nhà mặt tiền tại TP.HCM theo địa giới trước sáp nhập.
Đây là công cụ chạy bằng lệnh, chưa có giao diện web hoặc desktop.

## Trạng thái và phạm vi bản chia sẻ

Theo hồ sơ dự án ngày 09/11/2026, bộ dữ liệu cục bộ giữ 1.398 tin từ 1.426 HTML
chi tiết; chưa hoàn thành mục tiêu khoảng 2.000 tin. Khảo sát API đã xác minh
4 tin mới phù hợp, nhưng chưa nhập chúng vào bộ chính và chưa tích hợp API
vào luồng thu thập đầy đủ. Không suy ra website đã hết tin.

Repo chia sẻ mã nguồn, kiểm thử, [BRIEF](BRIEF_giai_doan_1.md) và
[kế hoạch](KE_HOACH_GIAI_DOAN_1.md). Không kèm CSV thật, HTML gốc, manifest,
log, trạng thái crawl, báo cáo nội bộ, hồ sơ người dùng hoặc khóa API.
HTML gốc có thể chứa thông tin liên hệ của người đăng nên không chia sẻ.
Các số liệu nêu trên là mốc bàn giao, không phải kết quả có thể tái lập chỉ
bằng cách tải repo này.

## Cài đặt và thử không gọi mạng

Môi trường dự án: Windows và Python 3.12.11. Chạy các lệnh PowerShell
bên dưới từ thư mục repo. Việc cài thư viện cần kết nối Internet.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --help
.\.venv\Scripts\python.exe scripts/check_shared.py
```

`check_shared.py` chạy các test độc lập với dữ liệu thật, chặn socket trong
suốt lượt kiểm thử và trả mã lỗi nếu có test thất bại. Test dùng fixture
nhân tạo và HTTP giả lập, không tải tin và không tạo bộ dữ liệu mẫu.

Hiện có 23 test thuộc bộ chia sẻ. 21 test còn lại không được chọn trong lệnh
này vì cần nguồn riêng tư: toàn bộ `test_saved_html.py`, `test_revision.py`,
ba test đọc hồ sơ trong `test_location_review.py`, một test robots thật trong
`test_api_probe.py` và một test HTML thật trong `test_api_html_probe.py`.
Script in danh sách test không được chọn; không đổi hoặc đánh dấu skip các
test gốc. Đây không phải chứng nhận toàn bộ 44 test đã đạt trên máy mới.

Nếu có đầy đủ kho dữ liệu cục bộ hợp lệ, chạy toàn bộ bằng:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Lệnh này sẽ lỗi thiếu file trên bản chỉ có mã nguồn; không tải lại dữ liệu
chỉ để chạy test.

## Thu thập và parse

Các lệnh sau thực sự truy cập website. Chỉ dùng khi chủ lượt thu thập đã
chấp thuận và đã kiểm tra điều kiện truy cập hiện tại của nguồn:

```powershell
.\.venv\Scripts\python.exe main.py pilot
# Chỉ chạy full sau khi đã kiểm tra pilot và được phép:
.\.venv\Scripts\python.exe main.py full
```

Pilot giới hạn 500 lượt truy cập; full giới hạn 3.000. Các giới hạn này áp
dụng cho từng lượt cục bộ, không phải bộ đếm dùng chung giữa nhiều máy.
Không chạy nhiều máy song song để vượt hạn mức của dự án. Mỗi lượt có
`run_state.json` ngăn khởi tạo lại; không xóa file đó để chạy lại. Client
kiểm tra robots, chờ giữa các lượt, không retry và dừng khi bị chặn.
Không bảo đảm cấu trúc hoặc số lượng tin trên website giữ nguyên.

Parse chỉ đọc offline, yêu cầu HTML và manifest đi kèm có hash hợp lệ:

```powershell
.\.venv\Scripts\python.exe main.py parse <thu_muc_raw_html> <file_csv_moi>
```

Không đưa HTML nguồn, thông tin liên hệ người đăng hoặc đầu ra chưa được
rà soát lên GitHub. Thiếu trường thì để rỗng; không tự suy tọa độ hoặc loại
diện tích. Giá trên m² tính từ giá chia diện tích chưa đủ để so sánh nếu
các tin dùng những loại diện tích khác nhau.

## Cấu trúc và script lịch sử

- `main.py`: CLI pilot, full và parse.
- `src/`: kiểm soát mạng, phân trang, parser, cleaner, kiểm chất lượng,
  thống kê và các module khảo sát API.
- `tests/`: test độc lập và test hồi quy cần dữ liệu riêng tư.
- `scripts/check_shared.py`: điểm vào kiểm thử của bản chia sẻ.
- `scripts/continue_*.py`, `survey.py`, `probe_*.py`: công cụ cho checkpoint
  lịch sử, cần state/manifest và có thể gọi mạng. Không phải lệnh bắt đầu
  dành cho máy mới. `continue_full.py` chưa hỗ trợ manifest hỗn hợp API/HTML.
- `scripts/verify_*.py`, `audit_sample.py`, `build_*`, `finalize_*`,
  `package_*`, `add_coordinate_conflict_evidence.py`: cần dữ liệu/hồ sơ
  cục bộ không nằm trong repo. Các gói báo cáo tạo ra cần được rà soát
  trước khi chia sẻ; không tự động đính kèm chúng vào issue hoặc GitHub.
- `scripts/cache_wheels.py`: công cụ môi trường cục bộ; repo không kèm kho wheel.

Đầu ra pilot nằm dưới `pilot/`; đầu ra full ở `data/`, `logs/`, `reports/`
và `outputs/`. Các thư mục này cùng `revisions/`, `analyses/`, `handoff/`,
`memory-bank/` và `.workspace/` được giữ cục bộ.

Các quyết định và ngoại lệ lịch sử trong BRIEF/kế hoạch chỉ mô tả lượt của
dự án gốc; chúng không cấp phép chạy tiếp các checkpoint trên máy mới.
Việc chia sẻ mã nguồn lần này được chủ dự án cho phép riêng. Repo GitHub
bắt đầu từ một bản mã nguồn sạch, không kèm lịch sử Git cũ có `NOTES.md`.
Lịch sử và dữ liệu của dự án gốc được giữ nguyên trên máy chủ dự án.
