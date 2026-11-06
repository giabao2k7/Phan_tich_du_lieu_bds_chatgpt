# Nhật ký, giả định và vấn đề

## 2026-11-02 — thực thi kế hoạch giai đoạn 1

- Người dùng yêu cầu đọc kế hoạch và thực thi. Tệp yêu cầu planner cũ chỉ là
  bối cảnh; công việc hiện tại là thực thi theo BRIEF. Lưu nguyên văn kế hoạch
  tại `KE_HOACH_GIAI_DOAN_1.md`. Chưa được phép full; dừng bàn giao sau pilot.
- Dùng 23 cột thực tế và 24 nhãn địa bàn trong bảng, ưu tiên hơn các tiêu đề
  “11 trường”/“22 đơn vị”. Các cột gốc lấy text từ nút HTML bằng get_text()
  không strip, không chuẩn hóa khoảng trắng; bỏ comment HTML không hiển thị.
- Khảo sát nằm trong pilot duy nhất: 1 request robots, 3 trang đầu ba nguồn,
  rồi nối tiếp thu thập dùng lại cache và cùng run_state/manifest. Hai script
  khảo sát kiểm tra chính xác trạng thái đầu vào; không chạy lại URL hay pilot.
  Constructor CLI từ chối mọi lần khởi tạo khi có run_state.
- Robots tải HTTP 200 cho phép ba nguồn; cấm API ngoài một số ngoại lệ và
  truy vấn q. Không dùng API, trình duyệt, proxy, VPN hoặc đổi danh tính.
  Request dùng User-Agent trung thực MosoResearch/1.0; tuần tự, không retry,
  delay 1,5 giây tính từ khi kết thúc request trước. Tính cả robots, khảo sát,
  lỗi và chuyển hướng vào trần 500/3000.
- HTML là Next.js streaming. Ghép $RS(source,target) trong DOM bản sao khi
  parse; giải mã self.__next_f từ HTML có sẵn. Dòng T có độ dài BYTE UTF-8,
  không được tách tất cả theo newline. HTML gốc không thay đổi. Không cần
  trình duyệt hoặc nguồn khác; BeautifulSoup vẫn đủ.
- tin_id chọn `_id` của đối tượng bất động sản trong HTML nhúng (24 ký tự),
  không phải ID trang/slug. `shortId` hiển thị “Mã tin” được ghi trong bằng
  chứng trường để đối chiếu. Tên file theo `_id`; ID không an toàn dùng hash.
- Đọc giá và diện tích từ dt/dd phần tin chính, không từ tiêu đề hoặc mô
  phỏng vay. Giá hiển thị có thể khác slug/tiêu đề do trang chưa cập nhật;
  ưu tiên “Mức giá”. Không lấy thông tin từ tin gợi ý.
- Ưu tiên diện tích chính có nhãn “Diện tích”; khi thiếu mới dùng nhãn diện
  tích cụ thể. Không gán loại cho diện tích tổng quát vì trang còn có thể
  hiển thị nhiều loại diện tích với số khác nhau. Thiếu để rỗng.
- Địa chỉ hiển thị lấy address cạnh h1. Quận cũ lấy rõ ràng từ
  pAddress.district trong đối tượng tin; chuỗi này lưu nguyên trong
  quan_phuong_goc. Không suy từ phường, không dùng newPropertyAddress cho
  quận cũ. Tin Thủ Đức giữ Thủ Đức dù tên phường ghi Quận 2 cũ.
- Chỉ nhận type=sale, loại hình được dt/dd xác minh và tỉnh/quận cũ đúng
  phạm vi. Loại không xác minh được ghi riêng, không đưa vào thống kê.
- Tọa độ chỉ lấy GeoJSON Point trực tiếp do tin cung cấp, thứ tự [kinh độ,
  vĩ độ]. Số phòng chỉ lấy nhãn hiển thị; không suy từ mô tả/tiêu đề.
- Ngày tương đối tính từ timestamp tải +07:00, không từ ngày parse. Không
  đổi “tháng trước” thành số ngày tùy ý. Lưu thuộc tính datetime vào bằng
  chứng để người dùng đánh giá sai lệch do làm tròn của trang.
- HTML nguồn chứa thông tin cá nhân (người đăng/liên hệ). Không xuất các
  trường này vào CSV, log hoặc báo cáo. Không commit raw HTML. Khi website
  yêu cầu gỡ sẽ dừng và xóa raw theo BRIEF.
- Full: 926 ID đầu duy nhất mỗi nguồn nhà trước lọc; không bù tin loại.
- Cảnh báo IQR: ngoài [P25−1,5×IQR, P75+1,5×IQR], số không dương và chênh
  giá/m² >10% so với giá tự tính. Chỉ gắn cờ, không xóa hoặc sửa outlier.
  Thống kê số hợp lệ dương, mean/median/min/max/P25/P75/P90 cho giá, diện
  tích và cả hai giá/m². Biểu đồ thang tuyến tính, giữ ngoại lệ; scatter ghi
  số mẫu không vẽ được do thiếu/không dương. Giá: tỷ đồng; diện tích: m²;
  thống kê giá/m² trong CSV là VND/m², quy đổi triệu bằng chia 1e6.
- Môi trường ban đầu: Python MSYS2 3.12.11 có requests 2.32.5, bs4 4.13.5,
  pandas 2.2.3, matplotlib 3.10.5 nhưng thiếu lxml; venv/ensurepip thất bại.
  Tải uv vào .runtime rồi cài CPython Windows native 3.12.11 riêng trong dự
  án; không đổi Python hệ thống. Venv khởi tạo được nhưng ensurepip bị lỗi
  trong sandbox; bootstrap pip qua uv vào venv. Kết quả môi trường sạch sẽ
  ghi riêng ở reports/environment.json; chưa kiểm chứng không coi là đạt.
- Lựa chọn html.parser của BeautifulSoup trong giai đoạn khảo sát để không
  chặn việc kiểm chứng HTML khi thiếu lxml. Sau cài đặt sẽ kiểm chứng lxml
  và khóa requirements; lựa chọn backend không thay đổi nguồn dữ liệu.

### Kết quả bổ sung khi đối chiếu offline

- Sau khi cài đủ thư viện, parser chính dùng BeautifulSoup + lxml. Khóa cả
  phụ thuộc gián tiếp theo môi trường đã cài trong requirements.txt.
- Mã `frontage` trong pTypeLvl0 xác minh nhà mặt tiền ngay cả khi DOM thiếu
  nhãn “Loại hình”; pType=alley_house xác minh nhà hẻm. Có test hồi quy trên
  HTML thật cho nhà mặt tiền giá 340 tỷ, diện tích 677 m². Không gán loại chỉ
  dựa trên nguồn danh sách khi thiếu bằng chứng của chính tin.
- Sửa hai lỗi giải mã Flight bằng kiểm tra hồi quy: byte UTF-8 cho dòng T
  và dòng gợi ý tài nguyên có ID rỗng (:HL/:HC). Không xóa/skip/xfail test.
- Pilot kết thúc 313 request = 1 robots + 15 danh sách + 297 chi tiết.
  Ba nguồn lần lượt gặp/tải 100, 98, 99 ID duy nhất; các trang vẫn tối đa 5,
  chênh số lượng do ID lặp giữa các trang theo thứ tự mặc định, không bù.
- Kiểm chứng môi trường mới dùng pip install -r requirements.txt --no-index
  --find-links .runtime/wheels. Wheel được đóng lại từ cache uv đã tải, xác
  minh từng hash và kích thước trong RECORD trước đóng. Nội dung package
  không thay đổi; chọn tag tương thích Python 3.12/Windows. Cách này tránh
  tải lại 50 MB. Chi tiết lệnh và hash CSV trong reports/environment.json.
- Một số tiến trình đọc file qua sandbox bị chậm ở pathlib.open. Đã dừng
  riêng các tiến trình chẩn đoán cũ trước khi tạo báo cáo cuối; không thay
  đổi HTML, bộ đếm request hoặc khởi tạo lượt crawl khác.
- Rà soát tỷ lệ thiếu: ngày có dạng tháng/năm không được ước tính bằng số
  ngày. Khi không quy đổi được chuỗi tương đối bằng phút/giờ/ngày/tuần,
  dùng ngày chính xác trong thuộc tính time[datetime] của chính tin, đổi
  sang +07:00. Đây là giá trị HTML có sẵn, không đoán tháng có bao nhiêu
  ngày. Những chuỗi tương đối đã hỗ trợ vẫn tính từ thoi_diem_crawl.
- Khi DOM không hiển thị số phòng nhưng đối tượng tin ghi rõ số nguyên
  dương pNumberOfBedrooms/pNumberOfBathrooms, lấy trực tiếp giá trị này.
  Không suy từ tiêu đề/mô tả và không biến giá trị null/0 mặc định thành
  phòng thực tế. Một tin ghi 23 phòng ngủ trong nguồn: giữ nguyên và rà soát.
- Hai chênh lệch giá/m² >10% được giữ nguyên để người dùng đánh giá:
  `6abf1c38a3b5530d263a95c1`: 15 tỷ / 73,54 m² = khoảng 203,97 triệu/m²,
  trong khi trang hiển thị 253,42 triệu/m²;
  `6ae45f37bfaa4b4f2be3ebdc`: 14 tỷ / 96,5 m² = khoảng 145,08 triệu/m²,
  trang hiển thị 112 triệu/m². Không thay giá hiển thị bằng giá tự tính.

### Bàn giao pilot

- 297 HTML chi tiết, 295 tin giữ (98 căn hộ, 98 nhà hẻm, 99 nhà mặt tiền),
  2 loại trừ: Thủ Dầu Một và một tin thiếu bằng chứng quận cũ. Không có
  trùng ID/URL, không có lỗi parse. Không còn thiếu ngày đăng chuẩn sau khi
  tận dụng time[datetime] với các chuỗi tháng/năm.
- 9 kiểm tra qua trong venv sạch; CSV tái lập giống từng byte khi chặn
  socket. Bằng chứng và SHA-256 tại reports/environment.json.
- Đối chiếu 21 tin với nút DOM nguồn, gồm 5 tin mỗi loại và các ca thiếu,
  Quận 2, hai chênh lệch giá/m². Bảng tại pilot/reports/manual_review.md.
- Đã mở kiểm tra trực quan cả ba PNG: nhãn tiếng Việt, đơn vị tỷ đồng/m²,
  số mẫu và ngoại lệ hiển thị đúng. CSV thống kê giữ đơn vị VND và VND/m².
- 313/500 request; khoảng cách bắt đầu nhỏ nhất 1,761841 giây. CLI pilot
  từ chối khởi tạo lại sau hoàn thành, không tăng bộ đếm. Chưa chạy full.
- Nghiệm thu pilot: mục 1,2,4,5,6 đạt với các giới hạn ghi trong báo cáo;
  mục 3 không đạt mục tiêu full vì mới pilot. Dừng chờ người dùng đánh giá.

## 2026-11-02 — hồ sơ đánh giá độc lập sau phản hồi người dùng

- Người dùng cung cấp 13 ID và yêu cầu nghiên cứu vấn đề vị trí, dữ liệu
  nguồn mâu thuẫn, diện tích thiếu và tin không còn xem được. Chỉ tổng hợp
  thông tin để mô hình khác tự xem xét kế hoạch/quy tắc; không đề xuất xử lý
  tại bước này. Đây là nhiệm vụ mới được người dùng yêu cầu, không phải một
  lần crawler thất bại hoặc cho phép chạy thêm lượt.
- Chỉ kiểm tra offline, chặn socket trong script lập hồ sơ. Không truy cập
  bản đồ/website, không geocode, không sửa CSV, HTML, parser hoặc bộ lọc.
  Request pilot giữ ở 313; chưa có full.
- Bằng chứng được tập hợp trong handoff/2026-11-02_review. Phân biệt phản hồi
  của người dùng với điều agent kiểm chứng từ HTML. Không tự xác nhận các
  khoảng lệch mét/km vì chưa có tọa độ đối chứng hoặc phép đo gốc.
- Đối chiếu Opal: mô tả nhắc Opal Boulevard/Phạm Văn Đồng, trường cấu trúc
  ghi Kha Vạn Cân/Thủ Đức. Chưa xác minh địa lý độc lập hoặc chốt nguồn đúng.
- Đối chiếu tin 6ae29887faae274494541131: có pLandArea=168 và “DTCN: 168m”
  trong mô tả, trong khi CSV diện tích rỗng. Ghi rõ khác biệt về nguồn và
  ý nghĩa diện tích, không điền giá trị hoặc gán loại diện tích mới.
- Ba tin người dùng báo không còn truy cập được có HTML HTTP 200 ở snapshot;
  không tải lại để xác định tình trạng hiện tại hoặc nguyên nhân.
- Bản nghiệm thu cũ được giữ như lịch sử. Hồ sơ mới giải thích kiểm tra
  deterministic/schema/nguồn không chứng minh độ đúng địa lý hay ngữ nghĩa.
- Chuẩn bị riêng gói tài liệu không HTML và các gói HTML bổ sung. Các gói
  HTML là bản nguồn nguyên vẹn có thể chứa thông tin liên hệ; chưa gửi đi.
- Kết quả audit: 297 HTML chi tiết khớp manifest; không có trường CSV nào
  khác chạy lại cùng parser; 290 cặp tọa độ xuất CSV đều khớp pLocation.
  Không coi điều này là kiểm chứng vị trí ngoài thực tế.
- Phát hiện thêm ba ca khác số giữa tọa độ nhúng: 0,026261 m; 350,499435 m;
  3.580,314698 m giữa pLocation và trường địa chỉ cũ/mới. Đây là khoảng
  cách nội bộ nguồn, không phải khoảng cách đến vị trí thật. Có phụ lục
  riêng và HTML nguồn cho cả ba ca, không chọn cặp số nào là đúng.
- Hoàn tất hồ sơ 17 ca chính + 3 ca tọa độ nội bộ, tổng 20; bản audit297,
  quy tắc 23 cột, giới hạn nghiệm thu, prompt và hướng dẫn upload. Gói
  chính không HTML, gói HTML20 và gói toàn bộ nguồn pilot được để riêng.


## 02/11/2026 — Triển khai sửa offline v2 theo đánh giá độc lập

Người dùng yêu cầu đọc đánh giá rồi làm; đã áp dụng D1–D8 theo phụ lục handoff/HOP_DONG_OFFLINE_V2_2026-11-02.md. Không chạy full, không request/geocode. Kết quả riêng tại revisions/2026-11-02_offline_v2, nguồn pilot và ba ZIP giữ nguyên.

Sửa parser vùng tin chính và Flight props/reference UTF-8; hợp nhất projection cùng ID nếu tương thích, lỗi minh bạch nếu xung đột; giữ nhãn diện tích cụ thể và các đại lượng song song. Không fallback pLandArea thành căn hộ. Tiền Decimal, từ chối giá ghép/dấu mơ hồ; tọa độ không bool, finite/range. Bỏ khác khoảng trắng/hoa thường chỉ khi so địa chỉ, giữ raw. Các regex chỉ tạo ứng viên tranh chấp, không chốt địa chỉ hoặc tài sản.

Đầu ra 297 parse, 0 lỗi; CSV 289, 6 ứng viên conflicted, 1 out_by_source, 1 unresolved; 2 ca asset unit unresolved vẫn trong compatibility CSV nhưng không phân tích theo loại. 280 ứng viên diện tích tái sinh, 254 nhãn CSV được phục hồi, 21 nhóm đa loại cùng số giữ riêng. 287 tin đủ điều kiện nguồn cho thống kê phù hợp; 286 giá dương, scatter chính 12/98/98 theo thông thủy/đất công nhận. Thang tuyến tính, giữ outlier; IQR riêng mỗi loại hình/đại lượng.

Không xóa/nới test cũ. Thêm 13 kiểm thử, tổng 22 đạt. Thay công khai scripts/verify_offline.py: chuyển sang verifier v2, so hai bản sửa mới thay vì yêu cầu giống CSV thuật toán cũ. Hai replay 27 tệp giống byte; 331 tệp nguồn được kiểm bảo toàn; code trước lưu code_before và code sau khóa code_hashes.json. Venv mới .verification/offline_v2_env: ensurepip thất bại trong môi trường hạn chế, đã bootstrap pip --python từ venv hiện có và cài wheel bằng --no-index. Đã mở xem cả 3 PNG; bằng chứng trong reports/manual_review.md và verification.json.

Còn cần đối chứng Opal, đơn vị tài sản 168/104, các pin và địa chỉ nghi vấn. Bốn trong sáu ứng viên phạm vi có thể chỉ khác dấu/tách trường; tách thận trọng không là chứng minh sai. Hai chênh giá/m² giữ nguyên. Chưa xác minh hiện trạng ba tin không xem được, chưa audit PII thủ công mọi HTML. Bàn giao BAO_CAO_BAN_GIAO.md và acceptance_final.md; full cần ủy quyền riêng.


## 02/11/2026 — Đối chứng vị trí ngoài MOSO được người dùng cho phép

Sau giải thích bước đối chứng, người dùng nói “ok, làm tiếp đi”. Phạm vi bổ sung công khai ở handoff/PHAM_VI_DOI_CHUNG_VI_TRI_2026-11-02.md. Đã rà 9 phản hồi pin + 2 xung đột lớn + 1 ca số nhỏ, tổng 12. Tạo bản riêng revisions/2026-11-02_location_review_v1; không đổi 398 tệp nguồn/pilot/v2 đã khóa, có kiểm hash Python và kiểm độc lập Get-FileHash. Không crawl MOSO, request pilot vẫn 313/500, full chưa chạy.

Bảy ca có tham chiếu dự án/cơ sở: Thịnh Vượng khoảng77m; Park ba tin1439/882/759m; Opal khoảng4km; Quỳnh Anh1004m; RES2G841m. Chưa có pin tài sản được xác minh tới căn/cổng/ranh thửa: verified_property_coordinates để null; các phép so chỉ là chênh tới điểm tham chiếu. Cả297 dòng trạng thái đều chặn khoảng cách thực địa chính xác. Không điều chỉnh điểm để khớp phản hồi người dùng.

Đọc web chính thức Đất Xanh2021 và PDF nhà thầu Phước Thành: Opal ở Dĩ An, Bình Dương cũ, song tin MOSO vẫn cần định danh đúng căn để kết luận ngoài phạm vi. Đọc trực quan PDF Intresco2009 trang43 và giấy đăng ký RES2021 trang1, hồ sơ Phước Thành trang22/31; không xuất thông tin cá nhân. Có mâu thuẫn phường15/24/25 của2G, nhiều marker ngoài nguồn; không chốt theo đa số. Geocoding số nhà2G trả nhầm2G35 bị từ chối. Không dùng iframe trụ sở/tâm viewport hoặc mọi schema geo làm pin tài sản. Điểm Park Rever khác CBRE được giữ riêng, không lấy trung bình.

Các nguồn trả403/429 không retry/né chặn; lỗiSSL không tắt chứng chỉ. HĐND trảHTML thayPDF và tài liệu thi hành án403: chỉ dùng trích đoạn tìm kiếm với giới hạn rõ. Các lượt khám phá web không được giả là đã nằm đầy đủ trong direct_requests.jsonl. Bộ thu nguồn riêng có cache, dựng báo cáo từ evidence hoàn toàn offline và chặn socket.

30/30 test đạt (22 test trước +8 test vị trí); dựng lại giống byte. Đã khóa hash code/evidence/build-inputs, có final_integrity.json. Năm ca chưa chọn điểm: Huỳnh Văn Chính thiếu định danh lô, Lê Lợi ẩn số nhà, Nguyễn Văn Đậu/Nguyễn Thái Sơn/Petroland ba mệnh đề,14A22 chưa khớp đúng căn, Sơn Kỳ chỉ khác0,026m. Hồ sơ cổng/tài sản hoặc định danh được cung cấp hợp lệ vẫn cần cho xác minh chính xác.
