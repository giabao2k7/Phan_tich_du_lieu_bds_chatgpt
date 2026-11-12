# BRIEF – Giai đoạn 1: Crawl và phân tích sơ bộ tin bán bất động sản moso.vn (TP.HCM)

> Tài liệu này mô tả yêu cầu của dự án. Vai trò cụ thể của bạn (lập kế hoạch hay thực thi code) sẽ được nêu riêng trong yêu cầu kèm theo. Nếu kế hoạch kèm theo mâu thuẫn với brief này, **brief này thắng**.

## 0. Nguyên tắc làm việc

- Báo cáo **trung thực**. Chưa kiểm tra thì không tuyên bố "xong" hay "đạt". Chưa đạt thì nói rõ chưa đạt và vì sao.
- Mọi giá trị trong dữ liệu phải đến từ HTML đã tải về. **Không** bịa, không sinh dữ liệu giả, không ghi đè hay hardcode kết quả.
- Gặp điều chưa rõ trong brief: tự quyết định hợp lý và ghi giả định vào `NOTES.md`. Chỉ hỏi lại khi không thể tiếp tục.
- **Không** chạy `git commit`, `git reset`, `git rebase`, `git push --force` hay bất kỳ lệnh nào sửa lịch sử git. Người dùng tự commit.
- Ghi vào `NOTES.md` mỗi lần làm việc: quyết định kỹ thuật, giả định, vấn đề chưa giải quyết.

## 1. Mục tiêu

Thu thập khoảng 2.000 tin **bán** nhà phố và căn hộ chung cư từ moso.vn khu vực TP.HCM (trước sáp nhập), làm sạch, lưu thành CSV, tạo thống kê cơ bản và biểu đồ phân bố. Kết quả dùng để người dùng xác định hướng đi cho một dự án phân tích lớn hơn, nên **độ chính xác của dữ liệu quan trọng hơn số lượng**.

## 2. Nguồn dữ liệu và phạm vi

Ba URL danh sách (bạn tự khảo sát cấu trúc trang):

| `loai_hinh` | URL |
|---|---|
| `can_ho` | https://moso.vn/ban-can-ho-chung-cu-thanh-pho-ho-chi-minh |
| `nha_hem` | https://moso.vn/ban-nha-hem-thanh-pho-ho-chi-minh-bff6mn |
| `nha_mat_tien` | https://moso.vn/ban-nha-mat-tien-thanh-pho-ho-chi-minh |

- Chỉ gửi request tới **moso.vn**. Tuân thủ `robots.txt`.
- Chỉ tin **bán** (không thuê); chỉ nhà phố (nhà hẻm, nhà mặt tiền) và căn hộ chung cư.
- Chỉ khu vực TP.HCM **trước khi sáp nhập**, tức 22 đơn vị cấp huyện liệt kê ở mục 5. Tin thuộc địa bàn Bình Dương hay Bà Rịa – Vũng Tàu cũ (nếu xuất hiện) phải loại bỏ và ghi số lượng loại vào báo cáo chất lượng.

## 3. Hạn mức và thứ tự lấy tin

| URL | Hạn mức |
|---|---|
| Căn hộ | Toàn bộ tin lấy được (dự kiến khoảng 148) |
| Nhà hẻm | 926 tin đầu tiên |
| Nhà mặt tiền | 926 tin đầu tiên |

- Giữ **thứ tự mặc định** của trang. Không đổi bộ lọc, không đổi cách sắp xếp.
- Pilot: **5 trang đầu** của mỗi URL.
- Nếu thu được ít hơn hạn mức, báo cáo rõ nguyên nhân. **Không** bù bằng nguồn khác hay bằng cách đổi bộ lọc.
- Không trùng `tin_id`. Pipeline phải tự xác định điều kiện dừng và không được lặp vô hạn; trần request ở mục 4 là chốt chặn cuối cùng.

## 4. Quy tắc crawl

- Request **tuần tự** (một request tại một thời điểm), delay **≥ 1,5 giây** giữa hai request.
- Trần request (tính cả trang danh sách và trang chi tiết): **pilot ≤ 500**, **full ≤ 3.000**. Cài bộ đếm trong code; chạm trần thì dừng, ghi log, báo cáo, **không tự nâng trần**.
- Giai đoạn 1 chỉ được chạy tối đa **một lần pilot và một lần full**. Các lượt sửa lỗi sau đó phải dùng lại HTML đã lưu qua lệnh `parse`.
- Lưu HTML gốc của từng tin tại `data/raw_html/<tin_id>.html`.
- Ghi `logs/requests.csv` gồm các cột: `url`, `thoi_diem` (ISO 8601), `status_code`.
- Gặp mã **403**, **429**, trang captcha hoặc dấu hiệu bị chặn: **dừng toàn bộ**, ghi log, báo cáo. **Không né tránh**: không dùng proxy, VPN, xoay IP, giả mạo danh tính hay vượt captcha.
- Nếu moso.vn yêu cầu dừng thu thập hoặc gỡ dữ liệu: dừng ngay và xóa dữ liệu thô.
- **Không thu thập thông tin cá nhân** (số điện thoại, tên người đăng, ...). Nếu HTML gốc chứa thông tin này, không đưa vào CSV và báo cáo trong `NOTES.md`.
- Công cụ mặc định: `requests` + `beautifulsoup4`. Chỉ đổi sang cách khác (API nội bộ, trình duyệt tự động) khi `bs4` thật sự không đủ, và phải ghi lý do vào `NOTES.md`.

## 5. Dữ liệu: 11 trường và hợp đồng đầu ra

**File chính:** `data/listings.csv`, mã hóa `utf-8-sig`. Mỗi dòng là một tin.

| Cột | Mô tả |
|---|---|
| `tin_id` | Định danh tin trên trang |
| `url` | URL trang chi tiết |
| `thoi_diem_crawl` | Thời điểm tải (ISO 8601) |
| `html_path` | Đường dẫn **tương đối** tới file HTML đã lưu |
| `loai_hinh` | `can_ho` / `nha_hem` / `nha_mat_tien` |
| `nhom_loai_hinh` | `can_ho` / `nha_pho` |
| `gia_goc` | Chuỗi giá đúng như trên trang |
| `gia_vnd` | Giá quy đổi sang VND (số nguyên) |
| `gia_m2_goc` | Chuỗi giá trên m² hiển thị trên trang |
| `gia_m2_vnd` | Giá trên m² hiển thị, quy sang VND |
| `gia_m2_tinh_vnd` | `gia_vnd / dien_tich_m2` (tự tính) |
| `dien_tich_goc` | Chuỗi diện tích đúng như trên trang |
| `dien_tich_m2` | Diện tích số, đơn vị m² |
| `loai_dien_tich` | Loại diện tích nếu trang ghi (ví dụ tim tường, thông thủy) |
| `quan_phuong_goc` | Chuỗi quận/phường nếu trang tách riêng khỏi địa chỉ |
| `dia_chi_goc` | Chuỗi địa chỉ đúng như trên trang |
| `quan_huyen_chuan` | Một trong 24 giá trị đóng bên dưới |
| `vi_do`, `kinh_do` | Tọa độ |
| `so_phong_ngu`, `so_phong_ve_sinh` | Số phòng |
| `ngay_dang_goc` | Chuỗi ngày đăng đúng như trên trang |
| `ngay_dang` | Ngày đăng dạng `YYYY-MM-DD` |

**Quy ước dữ liệu**

1. Luôn lưu **chuỗi gốc** đúng như trên trang, không sửa. Giá trị chuẩn nằm ở cột riêng.
2. Thiếu dữ liệu thì để **rỗng**. Không điền `0` hay giá trị mặc định.
3. Giá "thỏa thuận" hoặc không có số: `gia_vnd` để rỗng. Quy đổi đơn vị (tỷ, triệu) phải chính xác.
4. Diện tích: nếu trang ghi loại diện tích thì lưu vào `loai_dien_tich`; nếu không ghi thì để rỗng, **không đoán**.
5. Tọa độ: chỉ lấy khi **chính trang cung cấp**. Không tự suy ra từ địa chỉ, không dùng dịch vụ geocoding.
6. Ngày đăng dạng tương đối (ví dụ "2 ngày trước"): quy đổi theo `thoi_diem_crawl`, giữ chuỗi gốc ở `ngay_dang_goc`.
7. Phường: chỉ giữ chuỗi gốc, **không chuẩn hóa**.
8. `quan_huyen_chuan` chỉ nhận một trong 24 giá trị sau, ngoài ra để rỗng:

   `Quận 1`, `Quận 2`, `Quận 3`, `Quận 4`, `Quận 5`, `Quận 6`, `Quận 7`, `Quận 8`, `Quận 9`, `Quận 10`, `Quận 11`, `Quận 12`, `Bình Thạnh`, `Bình Tân`, `Gò Vấp`, `Phú Nhuận`, `Tân Bình`, `Tân Phú`, `Thủ Đức`, `Bình Chánh`, `Cần Giờ`, `Củ Chi`, `Hóc Môn`, `Nhà Bè`

   - Chỉ ghi `Quận 2` hoặc `Quận 9` khi **chính tin đăng ghi** như vậy. Tin ghi "Thủ Đức" thì giữ `Thủ Đức`.
   - **Không suy** quận từ tên phường. Trường hợp mơ hồ thì để rỗng.

## 6. Tự kiểm tra chất lượng dữ liệu

Trước khi báo hoàn thành pilot và full, bạn phải **tự viết code** kiểm tra và xuất `reports/data_quality.md`. Tối thiểu gồm:

- Trùng lặp (`tin_id`, `url`).
- Tỷ lệ thiếu của từng cột.
- Tính nhất quán đơn vị giá (ví dụ lẫn tỷ và triệu).
- Khoảng giá và diện tích hợp lý; chênh lệch giữa `gia_m2_vnd` và `gia_m2_tinh_vnd`.
- Số tin theo loại hình và theo `quan_huyen_chuan`; số tin bị loại do ngoài phạm vi.
- Danh sách các **nghi vấn chưa giải quyết** (báo cáo trước khi người dùng đánh giá mẫu).

## 7. Đầu ra phân tích

Trong thư mục `outputs/`:

- `summary_by_type.csv`: thống kê cơ bản theo `loai_hinh` cho giá, diện tích, giá trên m² (số lượng, trung bình, trung vị, nhỏ nhất, lớn nhất, các phân vị).
- Ít nhất 3 biểu đồ PNG: (1) phân bố giá theo loại hình; (2) scatter giá và diện tích, tách theo loại hình; (3) số tin theo `quan_huyen_chuan`.
- Trục có nhãn và đơn vị. Cách xử lý outlier và thang đo (có dùng log hay không) do bạn quyết định, giải thích ngắn trong `NOTES.md`.

## 8. Lệnh chạy

```
python main.py pilot
python main.py full
python main.py parse <thu_muc_html> <file_csv_ra>
```

- `pilot`: crawl theo quy tắc pilot, ghi toàn bộ đầu ra (dữ liệu, log, báo cáo, thống kê, biểu đồ) vào thư mục `pilot/` với cấu trúc giống thư mục gốc (`pilot/data/`, `pilot/logs/`, `pilot/reports/`, `pilot/outputs/`).
- `full`: crawl theo hạn mức mục 3, ghi vào `data/`, `logs/`, `reports/`, `outputs/` ở thư mục gốc.
- `parse`: parse **offline** từ HTML đã lưu, không gọi mạng, dùng **cùng logic parse** và cùng định dạng cột như hai lệnh trên.
- Mỗi lệnh phải chạy từ đầu đến cuối không cần can thiệp.

## 9. Bảng nghiệm thu (6 mục)

1. Một lệnh chạy được từ đầu đến cuối trên **môi trường sạch** (tạo `venv` mới, `pip install -r requirements.txt`, chạy) không lỗi.
2. Dữ liệu đúng phạm vi: chỉ tin bán, chỉ nhà phố và căn hộ chung cư, chỉ TP.HCM trước sáp nhập, không trùng ID.
3. Số lượng đạt khoảng 2.000 tin duy nhất theo hạn mức mục 3, hoặc báo rõ lý do nếu thiếu.
4. Đủ các cột theo mục 5; mỗi trường có cả chuỗi gốc và giá trị chuẩn; thiếu thì rỗng (không điền 0).
5. Đã lưu HTML gốc, có delay, có `logs/requests.csv` đúng định dạng, không có thông tin cá nhân.
6. Có bảng thống kê cơ bản và biểu đồ scatter, trục có nhãn và đơn vị đúng.

Khi báo "xong", hãy tự kiểm từng mục và ghi **đạt / không đạt** kèm bằng chứng. Người dùng sẽ kiểm tra **độc lập**, gồm đối chiếu dữ liệu với HTML đã lưu và với trang gốc.

## 10. Hành vi bị cấm

Các hành vi sau là vi phạm **nặng**, khiến giai đoạn bị tính là **không đạt** dù các kiểm tra khác có qua:

- Bịa dữ liệu; ghi đè hoặc hardcode kết quả; ghi trực tiếp vào CSV mà không đi qua pipeline.
- Sửa, xóa, bỏ qua (`skip`, `xfail`, `except` nuốt lỗi) hoặc nới ngưỡng của test và kiểm tra **mà không công khai**.
- Sửa lịch sử git.
- Né tránh việc bị chặn (mục 4).

Nếu bạn thay đổi một ngưỡng kiểm tra vì lý do kỹ thuật, ghi rõ lý do vào `NOTES.md`: đó là quyết định kỹ thuật chứ không phải vi phạm.

## 11. Môi trường và tiêu chuẩn mã nguồn

- Hệ điều hành **Windows**, **Python 3.12.11**, làm việc trong `venv` của repo hiện tại.
- Thư viện cho phép: `requests` (hoặc `httpx`), `beautifulsoup4` + `lxml`, `pandas`, `matplotlib` (hoặc `seaborn`, `plotly`). Ghi `requirements.txt` với **phiên bản cố định** (`==`).
- Dùng `pathlib`. Tên file HTML phải hợp lệ trên Windows (không chứa `\ / : * ? " < > |`). `html_path` là đường dẫn tương đối so với thư mục gốc.
- Tên hàm và biến bằng tiếng Anh; chú thích ngắn gọn bằng tiếng Việt.
- Mã nguồn dễ đọc cho người mới học Python. Tách rõ các bước: crawl, parse, clean, kiểm tra chất lượng, phân tích và vẽ biểu đồ.

## 12. Luồng làm việc của giai đoạn 1

1. Khảo sát trang và thiết kế pipeline.
2. Chạy `pilot`, chạy tự kiểm tra chất lượng, ghi nghi vấn vào `pilot/reports/data_quality.md`. **Báo cáo rồi dừng.** Không tự chạy `full`.
3. Người dùng đối chiếu một mẫu với trang gốc và gửi danh sách **bằng chứng lỗi**: bản ghi nào, trường nào, giá trị bạn lấy được, giá trị trên trang. Người dùng **không** hướng dẫn cách sửa; bạn tự quyết cách sửa. Sửa bằng cách dùng lại HTML đã lưu qua lệnh `parse`.
4. Khi người dùng cho phép, chạy `full`, tự chạy kiểm tra chất lượng, rồi tự kiểm theo bảng nghiệm thu ở mục 9.

## 13. Cách báo cáo mỗi lần báo xong

1. Bạn đã làm gì.
2. Kết quả tự kiểm từng mục nghiệm thu (đạt/không đạt, kèm bằng chứng).
3. Các giả định và nghi vấn còn lại.
4. Số request đã dùng so với trần.

## Bổ sung được duyệt sau lượt 1.508
Bạn duyệt nâng giới hạn nhà mặt tiền để tiếp tục hướng tới khoảng 2.000 tin sau lọc. Mức thực thi 1.550 ID nhà mặt tiền trước lọc, tái dùng dữ liệu cũ trong cùng trần full 3.000 lượt. Các quy tắc lọc và điều kiện dừng còn hiệu lực.
