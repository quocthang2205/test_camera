# Hướng dẫn sử dụng phần mềm Camera Checker

Phần mềm kiểm tra **pixel lỗi** của camera từ bộ ảnh chụp cố định: pixel nóng (hot), pixel chết (dead),
pixel kẹt (stuck) và lỗi camera nhiệt (IR). Kết quả xem ngay trong cửa sổ ứng dụng và xuất ra báo cáo PDF / JSON / CSV.

---

## 1. Cài đặt và mở phần mềm

### Cách A: dùng bản đã đóng gói (không cần cài Python)

| Hệ điều hành | File | Cách mở |
|---|---|---|
| Linux | `camera-checker` | `chmod +x camera-checker` rồi `./camera-checker` |
| macOS | `camera-checker` | Lần đầu: chuột phải > **Open**. Sau đó `./camera-checker` |
| Windows | `camera-checker.exe` | Bấm đúp. Nếu SmartScreen cảnh báo: **More info > Run anyway** |

Phần mềm là **ứng dụng desktop**: mở cửa sổ riêng, đóng cửa sổ là tắt (không cần trình duyệt, không cần terminal).
Lần mở đầu có thể chậm vài giây vì app tự giải nén.

| Hệ điều hành | Thành phần hiển thị | Cần cài thêm |
|---|---|---|
| Windows 10/11 | WebView2 (có sẵn trên Windows 11; Windows 10 cài WebView2 Runtime của Microsoft) | Không |
| macOS | WKWebView của hệ thống | Không |
| Linux | Qt WebEngine (đóng gói sẵn trong app) | Không (cần màn hình đồ hoạ X11 hoặc Wayland) |

### Cách B: chạy từ mã nguồn

```bash
cd ~/test_camera
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run_app.py        # mở cửa sổ ứng dụng
```

Trên Windows thay `.venv/bin/` bằng `.venv\Scripts\`.

---

## 2. Chuẩn bị ảnh

| Test | Ảnh cần chụp | Số ảnh |
|---|---|---|
| **hot** | Ảnh tối: che kín ống kính | 1, 5 hoặc 10 |
| **dead** | Ảnh nền trắng đều, sáng khoảng 60–80%, không cháy sáng | 1, 5 hoặc 10 |
| **stuck** | 5 cảnh: tối / trắng / đỏ / xanh lá / xanh dương | 1 ảnh mỗi cảnh |
| **ir** | Camera nhiệt, 2 mức nhiệt độ t1 và t2 | 1 ảnh mỗi mức |

Lưu ý khi chụp:
- Giữ nguyên **ISO, phơi sáng, độ phân giải** trong cùng một bộ ảnh.
- Dùng ảnh không nén mất dữ liệu (PNG, TIFF) nếu được; JPEG vẫn chạy nhưng có thể làm nhoè điểm lỗi.
- Đặt tên có tiền tố đúng ô: `dark_01.png`, `white_01.png`, `red_...`, `green_...`, `blue_...`, `t1_...`, `t2_...`.
  Khi đó có thể thả cả thư mục, ảnh tự vào đúng ô.
- Chạy nhầm bộ ảnh sẽ bị chặn: hot báo lỗi nếu ảnh sáng hơn 50 DN, dead báo lỗi nếu ảnh tối hơn 50 DN.

### Nên dùng bao nhiêu ảnh?

| Số ảnh | Ý nghĩa |
|---|---|
| **1** | Kiểm nhanh. Nhiễu ngẫu nhiên bị tính là lỗi nên có cảnh báo; không dùng để kết luận |
| **5** | Chuẩn. Lọc được nhiễu ngẫu nhiên |
| **10** | Kỹ. Lọc nhiễu tốt nhất, dùng khi cần kết luận chắc chắn |

Một pixel chỉ được tính là **lỗi thật** khi bị flag ở **tất cả** ảnh được phân tích (chỉnh được bằng thông số
"Tỉ lệ frame phải lỗi"). Điểm chỉ xuất hiện ở một vài ảnh được xem là **nhiễu** và bị loại.

---

## 3. Dùng giao diện web

Giao diện có 4 bước, làm từ trên xuống:

1. **Chọn loại test**: Pixel nóng, Pixel chết, Pixel kẹt hoặc Camera nhiệt.
2. **Thêm ảnh**: kéo thả ảnh hoặc cả thư mục vào ô (thả ra ngoài ô thì ảnh tự vào đúng ô theo tên file), hoặc **bấm vào ô** để chọn thêm ảnh từ máy tính. Mỗi lần thả hoặc chọn là **thêm tiếp** vào ô, ảnh trùng bị bỏ qua; nút `×` góc ô xoá hết ảnh trong ô.
   Với hot và dead, chọn **Số ảnh phân tích**: `1 · kiểm nhanh`, `5 · chuẩn` hoặc `10 · kỹ`.
   Nếu thả nhiều ảnh hơn số đã chọn, phần mềm dùng các ảnh đầu theo thứ tự tên file.
3. **Điều kiện chụp** (không bắt buộc): camera, serial, firmware, ISO, phơi sáng, bitrate, FPS, nhiệt độ,
   người test, ghi chú. Camera, ISO và phơi sáng tự đọc từ EXIF nếu ảnh có; nhập tay sẽ ưu tiên hơn.
4. **Thông số phân tích** (không bắt buộc): để trống là dùng giá trị mặc định. Ô nào khác mặc định sẽ được tô màu
   và ghi vào báo cáo.

Bấm **Phân tích** (hoặc `Ctrl+Enter`). Ảnh 4K xử lý mất vài giây.

### Đọc kết quả

- **Thẻ tổng hợp**: số điểm lỗi theo từng loại, trong đó có số điểm ở vùng giữa A và phân loại đơn / cụm / đường.
- **Vị trí điểm lỗi (tổng hợp)**: ảnh đầu tiên có vòng tròn đánh dấu lỗi thật. Bật/tắt từng lớp, bấm vào vòng tròn
  hoặc dòng trong bảng để **phóng to** vùng quanh điểm đó (có giá trị màu tại tâm). Bảng lọc được theo kết quả,
  vùng và loại.
- **Từng ảnh đã phân tích** (hot và dead): bảng tổng hợp theo ảnh (bị flag / lỗi thật / nhiễu loại) và lưới tất cả
  5 hoặc 10 ảnh, mỗi ảnh có đánh dấu riêng. **Vòng đặc** là lỗi thật, **vòng đứt nét** là nhiễu bị loại.
- **Nút tải**: báo cáo PDF, tất cả kết quả `.json`, danh sách điểm `.csv`, và từng file `.json` riêng.

### Phân loại điểm lỗi

| Loại | Ý nghĩa |
|---|---|
| **Đơn** | 1 pixel lỗi đứng riêng |
| **Cụm** | Từ 2 pixel lỗi liền nhau trở lên, không thành đường |
| **Đường** | Cụm mảnh và dài (mặc định dài từ 10 px, rộng tối đa 2 px) |
| **Vùng A** | Khung giữa ảnh (mặc định từ 1/4 đến 3/4 mỗi chiều); phần còn lại là vùng B |

### Ý nghĩa từng test

| Test | Cách phát hiện |
|---|---|
| **hot** | Pixel sáng hơn median lân cận quá ngưỡng (mặc định 40 DN) trên ảnh tối |
| **dead** | Pixel tối hơn mức % của median lân cận (mặc định dưới 50%) trên ảnh nền trắng |
| **stuck** | Lệch lân cận ở cả 5 cảnh nhưng giá trị gần như không đổi giữa các cảnh |
| **ir** | So đáp ứng giữa t2 và t1: pixel kẹt (không phản ứng), chết (phản ứng yếu), nóng (phản ứng quá mạnh). Nếu đáp ứng dưới 20 DN (AGC đang bật) thì chuyển sang chế độ outlier |

---

## 4. Báo cáo PDF

Bấm **Tải báo cáo PDF** trên web, hoặc dòng lệnh tự sinh file `<tên>.pdf`. Nội dung:

1. Kết luận nhanh: số điểm lỗi và số điểm ở vùng giữa A.
2. Điều kiện chụp.
3. Kết quả tổng hợp, kèm bảng theo từng ảnh (hot và dead).
4. Thông số phân tích (dấu `*` là khác mặc định).
5. Ảnh tổng hợp đánh dấu vị trí lỗi.
6. Lưới từng ảnh đã phân tích (5 hoặc 10 ảnh, mỗi ảnh đánh dấu riêng).
7. Danh sách điểm lỗi (tối đa 300 dòng; đầy đủ ở `.json` và `.csv`).

Font có dấu tiếng Việt đã đóng gói sẵn trong phần mềm nên PDF hiển thị đúng trên mọi máy.

---

## 5. Dùng dòng lệnh

Luôn đặt pattern ảnh trong **ngoặc kép**. Ví dụ với bản chạy từ mã nguồn:

```bash
cd ~/test_camera
.venv/bin/python -m camera_checker hot "samples/defects/hot/dark_*.png"             # 5 ảnh (chuẩn)
.venv/bin/python -m camera_checker hot "samples/defects/hot/dark_*.png" -n 10       # 10 ảnh (kỹ)
.venv/bin/python -m camera_checker hot "samples/defects/hot/dark_01.png" -n 1       # 1 ảnh (kiểm nhanh)
.venv/bin/python -m camera_checker dead "samples/defects/dead/white_*.png" -n 10
.venv/bin/python -m camera_checker stuck "dark_*.png" "white_*.png" "red_*.png" "green_*.png" "blue_*.png"
.venv/bin/python -m camera_checker ir "t1_*.png" "t2_*.png"
```

Một số tuỳ chọn hay dùng:

```bash
-o ten_file                  # tên file kết quả (mặc định theo tên test)
--camera "TÊN" --serial SN-0012 --firmware v1.2.3 --iso 800 --bitrate 50Mbps
--t-dev 30 --kernel 7        # đổi thông số phân tích
--no-pdf                     # không sinh PDF
.venv/bin/python -m camera_checker hot -h      # xem đầy đủ tuỳ chọn
```

So sánh hai lần đo (ví dụ trước và sau burn-in):

```bash
.venv/bin/python -m camera_checker compare hot_lan1.json hot_lan2.json --tol 3
```

Với bản đã đóng gói, dòng lệnh vẫn nằm ở mã nguồn; bản đóng gói chỉ mở giao diện web.

---

## 6. Ảnh mẫu để thử

Sinh bộ ảnh 4K có gắn sẵn lỗi (mỗi bộ hot và dead có 10 lỗi cố định kèm nhiễu ngẫu nhiên):

```bash
.venv/bin/python scripts/generate_defect_samples.py
```

Ảnh ra ở `samples/defects/{hot,dead,stuck,ir}/`. Thả thư mục tương ứng vào web, kết quả mong đợi:

| Bộ | Kết quả đúng |
|---|---|
| hot, 5 hoặc 10 ảnh | 10 lỗi (6 đơn, 2 cụm, 2 đường), 5 điểm ở vùng A |
| dead, 5 hoặc 10 ảnh | 10 lỗi như trên |
| hot hoặc dead, 1 ảnh | 70 lỗi (10 thật và 60 nhiễu) kèm cảnh báo |
| stuck | 10 lỗi |
| ir | 2 kẹt, 2 chết, 2 nóng |

---

## 7. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Cửa sổ trắng hoặc không hiện (Windows) | Cài WebView2 Runtime của Microsoft |
| Linux báo lỗi `xcb` / không mở được cửa sổ | Cần phiên đồ hoạ; nếu thiếu thư viện: `sudo apt install libxcb-cursor0` |
| `chỉ có N ảnh, cần M` | Thả thêm ảnh hoặc chọn số ảnh nhỏ hơn. Với dòng lệnh, kiểm tra ngoặc kép quanh pattern |
| `ảnh quá sáng cho test hot` | Đang dùng nhầm ảnh sáng; chụp lại ảnh tối, che kín ống kính |
| `ảnh quá tối cho test dead` | Đang dùng nhầm ảnh tối; cần ảnh nền trắng đều |
| `kích thước ... khác ...` | Các ảnh trong một bộ phải cùng độ phân giải |
| Quá nhiều điểm lỗi, toàn nhiễu | Tăng số ảnh lên 5 hoặc 10, hoặc tăng ngưỡng lệch lân cận |
| Không tạo được PDF | Báo lỗi hiện trên web; kết quả `.json` và `.csv` vẫn tải được |
| macOS không cho mở | Chuột phải vào file > **Open** > **Open** |
| Windows cảnh báo SmartScreen | **More info > Run anyway** |

Nút tải PDF / JSON / CSV trong cửa sổ ứng dụng sẽ hỏi nơi lưu file.

Phần mềm không lưu ảnh trên máy chủ giữa các lần gọi. Tổng dung lượng ảnh mỗi lần phân tích tối đa 2 GB.
