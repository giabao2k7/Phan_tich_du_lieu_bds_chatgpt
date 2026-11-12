# Kế hoạch giai đoạn 1 — Thu thập và phân tích tin bán bất động sản moso.vn

**1. Hướng tiếp cận tổng thể**

Ưu tiên dữ liệu chính xác, truy xuất được về HTML nguồn. Pipeline tách thành: tải trang → lưu HTML và thông tin tải → trích xuất → chuẩn hóa → kiểm tra → phân tích.

Chỉ triển khai giai đoạn 1 theo BRIEF. Chưa khảo sát website; không giả định cấu trúc HTML, phân trang hoặc số lượng thực tế. Agent thực thi phải xác minh các điểm này. BRIEF được ưu tiên khi có mâu thuẫn.

Chạy tối đa một lượt pilot và một lượt full. Sau pilot phải báo cáo rồi dừng; full chỉ chạy khi người dùng cho phép. Sửa lỗi bằng HTML đã lưu, không tải lại.

Bổ sung theo quyết định của bạn sau khi lượt full dừng ở lượt truy cập 185: cho phép tiếp tục một lần sau lỗi kết nối không có phản hồi HTTP. Dùng lại HTML và nhật ký đã lưu, kiểm tra lại robots.txt và thử tiếp từ tin chưa tải, trong cùng trần 3.000 lượt. Giữ các điều kiện dừng của BRIEF. Nếu phần tiếp tục lại dừng do lỗi truy cập, lưu và báo cáo phần đã thu.

Sau khi dừng ở lượt 457, bạn yêu cầu tiếp tục từ điểm này theo cùng các điều kiện. Mỗi lần nối chỉ được khởi tạo một lần cho điểm dừng đã duyệt.

Sau khi dừng ở lượt 499, bạn yêu cầu nối tiếp từ điểm này theo cùng các điều kiện.

**2. Cấu trúc thư mục và module dự kiến**

```text
main.py
requirements.txt
README.md
NOTES.md
src/
  config.py
  crawler.py
  parser.py
  cleaner.py
  quality.py
  analysis.py
tests/
data/
  raw_html/
  list_html/
  manifest.jsonl
  run_state.json
  listings.csv
logs/
  requests.csv
reports/
  data_quality.md
  exclusions.csv
  acceptance.md
outputs/
  summary_by_type.csv
  price_distribution.png
  price_area_scatter.png
  district_counts.png
pilot/
  data/
  logs/
  reports/
  outputs/
```

`pilot/` có cấu trúc đầu ra giống lượt full. `manifest.jsonl` lưu URL, thời điểm tải, đường dẫn HTML, nguồn danh sách và thứ tự xuất hiện để tái lập offline. `run_state.json` lưu lượt đã bắt đầu, bộ đếm request và nguyên nhân kết thúc, ngăn vô tình chạy lại.

Dùng `pathlib`; `html_path` luôn tương đối với gốc repo, kể cả `pilot/data/...`. Không sửa HTML nguồn.

**3. Các bước thực hiện**

**Bước 1 — Chốt hợp đồng và chuẩn bị môi trường**

- **Mục tiêu:** thống nhất quy tắc trước khi gửi request.
- **Thực hiện:** dùng Windows, Python 3.12.11; tạo môi trường sạch. Chọn `requests`, `beautifulsoup4`, `lxml`, `pandas`, `matplotlib`; khóa phiên bản đã kiểm chứng bằng `==`. Định nghĩa đủ **23 cột thực tế** trong bảng mục 5, đúng thứ tự; tiêu đề “11 trường” không thay thế bảng. Ghi giả định vào `NOTES.md`.
- **Kiểm chứng:** kiểm tra phiên bản, cài đặt và import thư viện; kiểm tra schema, ba loại hình, hai nhóm và tập 24 giá trị địa bàn.
- **Hoàn thành:** môi trường hoạt động, hợp đồng đầu ra và cấu hình hạn mức rõ ràng. Chưa tuyên bố crawler hoạt động.

**Bước 2 — Xây lớp tải có kiểm soát**

- **Mục tiêu:** mọi truy cập đều tuân thủ BRIEF.
- **Thực hiện:** mọi request đi qua một lớp duy nhất, tuần tự, chờ ít nhất 1,5 giây sau request trước. Chỉ cho phép hostname `moso.vn`; kiểm tra chuyển hướng trước khi theo, không tự theo sang miền khác. Đọc và tuân thủ `robots.txt` trước các trang nội dung.
- Tính bảo thủ cả robots, khảo sát, chuyển hướng và lần thử thất bại vào ngân sách: pilot 500, full 3.000. Không tự retry. Lưu bộ đếm trước khi gửi; log đúng ba cột yêu cầu. Lỗi không có phản hồi HTTP để trống `status_code`, mô tả riêng trong báo cáo.
- Dừng toàn bộ khi 403, 429, captcha hoặc dấu hiệu chặn; không đổi công cụ để vượt chặn. Robots không xác minh được thì dừng, báo nguyên nhân.
- **Kiểm chứng:** kiểm tra offline bộ đếm, delay, chặn miền ngoài và điều kiện dừng bằng phản hồi mô phỏng; không tạo tin giả vào dữ liệu.
- **Hoàn thành:** cơ chế giới hạn và lưu trạng thái đã được kiểm tra.

**Bước 3 — Khảo sát trong ngân sách pilot và lưu nguồn**

- **Mục tiêu:** xác minh phân trang, ID và nguồn từng trường.
- **Thực hiện:** coi request khảo sát đầu tiên là bắt đầu lượt pilot duy nhất. Lưu ngay robots, HTML danh sách, HTML chi tiết và metadata; tái dùng trang đã tải trong lượt này.
- Khảo sát ba URL trong BRIEF, giữ thứ tự mặc định. Xác định liên kết trang tiếp theo, ID thực, dấu hiệu tin bán, loại hình, địa bàn và selector từng trường. Không coi “không tìm thấy selector” là danh sách rỗng hợp lệ.
- Pilot lấy tin trên tối đa năm trang đầu mỗi nguồn. Dừng nguồn khi hết trang, lặp URL/nội dung hoặc không còn ID mới; chạm trần hay bị chặn thì dừng toàn bộ. Khử trùng ID và URL trước tải chi tiết.
- **Kiểm chứng:** đối chiếu liên kết và trường trích xuất với HTML đã lưu; xác nhận thứ tự và số trang.
- **Hoàn thành:** có bản đồ trích xuất dựa trên bằng chứng và kho nguồn pilot, hoặc báo rõ điểm dừng. Không mở thêm lượt crawl để sửa lỗi.

**Bước 4 — Parse và chuẩn hóa offline**

- **Mục tiêu:** tạo CSV có thể tái lập.
- **Thực hiện:** ba lệnh dùng chung parser và cleaner. `parse` tuyệt đối không gọi mạng; đọc manifest kèm HTML để giữ nguyên thời điểm tải, URL và nguồn. Thiếu metadata cần thiết phải báo lỗi, không lấy thời gian sửa file thay thế.
- Giữ chuỗi gốc; chuẩn hóa ở cột riêng. Thiếu thì rỗng. Giá thỏa thuận không quy thành số; kiểm tra đơn vị tỷ/triệu và dấu phân cách. Chỉ tính giá/m² khi có giá và diện tích dương; không thay giá/m² hiển thị bằng giá tự tính.
- Ngày tương đối dựa trên thời điểm tải có múi giờ `+07:00`; không dùng ngày chạy lại parser. Không đoán loại diện tích, tọa độ, số phòng hay quận từ phường.
- Loại tin thuê, sai loại hình, ngoài địa bàn; ghi ID, lý do và bằng chứng trong báo cáo loại trừ. Tin chưa đủ bằng chứng địa bàn được tách khỏi dữ liệu phân tích, báo riêng.
- **Kiểm chứng:** đối chiếu tối thiểu 15 tin nếu đủ, phân bổ ba loại hình và bổ sung ca thiếu/mơ hồ. Chạy lại offline phải cho cùng dữ liệu.
- **Hoàn thành:** CSV `utf-8-sig`, đủ schema, không trùng, mọi giá trị có nguồn hoặc phép biến đổi được giải thích.

**Bước 5 — Kiểm tra, phân tích và bàn giao pilot**

- **Mục tiêu:** cung cấp mẫu có thể đánh giá độc lập.
- **Thực hiện:** tự động báo trùng ID/URL, thiếu từng cột, đơn vị giá, khoảng giá/diện tích, chênh lệch hai giá/m², số tin theo loại hình/địa bàn và số loại trừ.
- Cảnh báo số không dương, ngoại lệ theo IQR và chênh lệch giá/m² trên 10%; đây là ngưỡng rà soát, không tự xóa hoặc sửa giá trị. Ghi công thức, ngưỡng và thay đổi vào `NOTES.md`.
- Thống kê giá, diện tích và cả hai giá/m²: số hợp lệ, trung bình, trung vị, min, max, P25/P75/P90. Xuất ba PNG đúng BRIEF; dùng tỷ đồng, m², triệu đồng/m². Giữ outlier; ghi rõ nếu dùng thang log và số điểm không vẽ được.
- **Kiểm chứng:** mở CSV và PNG; kiểm tra nhãn, đơn vị, số mẫu, đường dẫn HTML; đối chiếu log với bộ đếm.
- **Hoàn thành:** đủ đầu ra pilot và danh sách nghi vấn. Báo sáu mục nghiệm thu với bằng chứng, phân biệt kết quả pilot và mục tiêu full chưa kiểm chứng. **Dừng chờ người dùng đánh giá.**

**Bước 6 — Sửa offline, chạy full và nghiệm thu**

- **Mục tiêu:** hoàn thiện kết quả sau phản hồi.
- **Thực hiện:** chuyển bằng chứng lỗi thành kiểm tra hồi quy trên HTML thật; sửa logic rồi chạy `parse`, tái tạo báo cáo và biểu đồ. Không sửa tay CSV.
- Chỉ khi được phép mới chạy full một lần: toàn bộ căn hộ, 926 tin đầu nhà hẻm, 926 tin đầu nhà mặt tiền. Mỗi lượt giữ metadata riêng.
- **Kiểm chứng:** chạy các kiểm tra bước 4–5; đối chiếu thêm mẫu full. Kiểm tra môi trường sạch bằng parse offline, không crawl lại để nghiệm thu.
- **Hoàn thành:** báo sáu mục đạt/không đạt kèm bằng chứng, số request/trần, thiếu hụt và nguyên nhân, giả định và nghi vấn còn lại. Không che lỗi hoặc tự nâng trần.

**4. Giả định, điều chưa biết và rủi ro**

- **Hạn mức 926:** hiểu bảo thủ là 926 ID đầu tiên duy nhất gặp theo thứ tự nguồn, trước lọc; không lấy tin phía sau để bù tin loại. Báo riêng số gặp, tải thành công, loại và giữ.
- **22 địa bàn/24 nhãn:** dùng tập 24 nhãn mục 5; Quận 2/9 chỉ khi tin ghi rõ. Địa bàn không rõ không suy từ phường.
- **HTML chứa thông tin cá nhân:** không trích xuất người đăng/điện thoại vào CSV, log hay báo cáo; ghi sự hiện diện trong HTML vào NOTES. Nếu website yêu cầu gỡ, dừng và xóa dữ liệu thô theo BRIEF.
- **Trang động hoặc cấu trúc đổi:** chỉ đổi công cụ khi có bằng chứng `bs4` không đủ, vẫn giữ giới hạn miền, request và chống chặn.
- **ID không an toàn trên Windows:** giữ nguyên ID trong CSV, dùng tên file mã hóa an toàn và lưu ánh xạ; ghi ngoại lệ.
- **Lượt crawl hỏng:** giữ phần đã tải, sửa offline; không tự chạy lượt thứ hai. Không commit hoặc sửa lịch sử git.

Bổ sung sau khi bạn duyệt nâng giới hạn: nối từ mốc 1.508 sau lượt full hoàn tất; nâng riêng nhà mặt tiền lên 1.550 ID duy nhất trước lọc để hướng tới khoảng 2.000 tin sau lọc. Tái dùng trang và HTML cũ, kiểm robots trước tải mới, giữ trần gộp 3.000 lượt và mọi điều kiện dừng. Ước tính thêm khoảng 650 lượt nếu nguồn còn tin và không lỗi; tối đa 624 HTML chi tiết mới. Dừng khi đạt giới hạn mới, hết tin mới, nguồn từ chối hoặc chạm trần. Tiêu chí hoàn tất là lưu nguồn, xuất bản CSV gộp riêng và phiếu kiểm tra, báo số gặp/tải/loại/giữ. Dữ liệu sẽ tăng tỷ trọng nhà mặt tiền.
