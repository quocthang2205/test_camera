# Kiểm tra pixel lỗi camera

Phát hiện pixel nóng (hot), chết (dead), kẹt (stuck) và lỗi camera nhiệt (IR) từ bộ ảnh chụp cố định.
Mỗi kết quả kèm điều kiện chụp: độ phân giải (tự nhận biết), ISO, bitrate, tên camera.

## Cài đặt (một lần)

```bash
cd ~/test_camera
python3 -m venv .venv
.venv/bin/pip install numpy opencv-python-headless scipy flask fpdf2
```

## Chuẩn bị ảnh

| Test  | Ảnh cần chụp                                         | Số ảnh tối thiểu  |
|-------|------------------------------------------------------|-------------------|
| hot   | Ảnh tối: che kín ống kính                            | 5 (chọn được 1–5) |
| dead  | Ảnh nền trắng đều, sáng khoảng 60–80%, không cháy    | 5 (chọn được 1–5) |
| stuck | 5 cảnh: tối / trắng / đỏ / xanh lá / xanh dương      | 1 mỗi cảnh        |
| ir    | Camera nhiệt: 2 mức nhiệt độ t1, t2                  | 1 mỗi mức         |

Giữ nguyên ISO, phơi sáng và độ phân giải trong cùng một bộ ảnh.
Chạy nhầm bộ ảnh sẽ bị chặn: hot báo lỗi khi ảnh sáng hơn 50 DN, dead báo lỗi khi ảnh tối hơn 50 DN.

## Báo cáo PDF

Mỗi lần chạy tự sinh báo cáo `<tên kết quả>.pdf` cạnh file `.json` (tắt bằng `--no-pdf`).
Trên web: bấm **Tải báo cáo PDF** ở phần kết quả.

Nội dung: kết luận nhanh (số điểm lỗi, số điểm ở vùng A), điều kiện chụp, bảng tổng hợp, thông số phân tích
(đánh dấu `*` thông số khác mặc định), ảnh đánh dấu vị trí lỗi, danh sách điểm lỗi (tối đa 300 dòng;
danh sách đầy đủ ở `.json` / `.csv`).

Cần font có dấu tiếng Việt: Linux dùng DejaVu (`sudo apt install fonts-dejavu-core`), Windows/macOS dùng Arial.

## Chạy bằng dòng lệnh

Luôn đặt pattern ảnh trong ngoặc kép.

```bash
# Pixel nóng: ảnh tối, ghi kèm ISO và bitrate
.venv/bin/python -m camera_checker hot "dark_*.jpeg" --iso 800 --bitrate 50Mbps

# Pixel chết: ảnh nền trắng
.venv/bin/python -m camera_checker dead "white_*.jpeg" --iso 100 --bitrate 50Mbps

# Pixel kẹt: 5 cảnh theo thứ tự dark white red green blue
.venv/bin/python -m camera_checker stuck "dark_*.jpeg" "white_*.jpeg" "red_*.jpeg" "green_*.jpeg" "blue_*.jpeg"

# Camera nhiệt
.venv/bin/python -m camera_checker ir "t1_*.png" "t2_*.png"

# Chọn số ảnh phân tích (hot/dead): -n 1 = kiểm nhanh, mặc định 5 = chuẩn, -n 10 = kỹ
.venv/bin/python -m camera_checker hot "samples/Test_1.jpeg" -n 1
.venv/bin/python -m camera_checker hot "dark_*.jpeg" -n 10    # có 12 ảnh vẫn chỉ dùng 10 ảnh đầu theo tên

# Đặt tên file kết quả riêng cho từng lần đo (mặc định hot -> hot.json)
.venv/bin/python -m camera_checker hot "dark_*.jpeg" --iso 800 -o hot_iso800

# So sánh 2 lần đo: điểm mới xuất hiện / biến mất; cảnh báo nếu khác độ phân giải, ISO, bitrate
.venv/bin/python -m camera_checker compare hot_lan1.json hot_lan2.json
```

Về số ảnh: pixel chỉ bị tính là lỗi khi lỗi ở **tất cả** ảnh được phân tích. Dùng 5 ảnh sẽ lọc được nhiễu
ngẫu nhiên; dùng 10 ảnh cho kết quả kỹ nhất; dùng 1–4 ảnh thì chương trình in WARNING, chỉ nên dùng để kiểm nhanh, kết luận cuối cần 5 ảnh.

Xem đủ tuỳ chọn: `.venv/bin/python -m camera_checker hot -h`

### Ghi đủ điều kiện chụp và chỉnh thông số phân tích

```bash
# Điều kiện chụp (đều tuỳ chọn, ghi vào file kết quả)
.venv/bin/python -m camera_checker hot "dark_*.jpeg" --camera "GREMSY INFISIGHT" --serial SN-0012 --firmware v1.2.3 \
    --iso 800 --exposure "1/60 s" --bitrate 50Mbps --fps 30 --temperature 25°C --tester Thang --note "sau burn-in 24h"

# Thông số phân tích (bỏ qua = mặc định). Mỗi chế độ chỉ có các cờ nó dùng, xem bằng -h
.venv/bin/python -m camera_checker hot "dark_*.jpeg" --t-dev 30 --hit-pct 80 --kernel 7 --edge 8 --zone-a-pct 60

# So sánh với dung sai vị trí tuỳ chỉnh (mặc định 2 px)
.venv/bin/python -m camera_checker compare lan1.json lan2.json --tol 3
```

| Cờ                | Mặc định | Chế độ      | Ý nghĩa                                                    |
|-------------------|----------|-------------|------------------------------------------------------------|
| `--t-dev`         | 40       | hot, stuck  | DN lệch khỏi median lân cận thì tính là lỗi                |
| `--dead-pct`      | 50       | dead        | pixel tối hơn x % median lân cận là pixel chết             |
| `--hit-pct`       | 100      | hot, dead   | % số frame pixel phải lỗi                                  |
| `--stuck-flat`    | 10       | stuck       | DN dao động tối đa giữa 5 cảnh                             |
| `--dark-max`      | 50       | hot         | median ảnh tối tối đa (chặn nhầm bộ ảnh)                   |
| `--white-min`     | 50       | dead        | median ảnh trắng tối thiểu (chặn nhầm bộ ảnh)              |
| `--ir-min-resp`   | 20       | ir          | đáp ứng t2−t1 dưới mức này -> chế độ outlier (AGC)         |
| `--ir-dev`        | 30       | ir          | DN lệch lân cận cho IR                                     |
| `--ir-stuck-ratio`| 0.1      | ir          | kẹt: đáp ứng < x · median                                  |
| `--ir-dead-ratio` | 0.5      | ir          | chết: đáp ứng < x · median                                 |
| `--ir-hot-ratio`  | 1.5      | ir          | nóng: đáp ứng > x · median                                 |
| `--kernel`        | 9        | tất cả      | cửa sổ median, px (số lẻ)                                  |
| `--edge`          | 4        | tất cả      | bỏ qua mép ảnh, px                                         |
| `--zone-a-pct`    | 50       | tất cả      | vùng giữa A chiếm x % chiều rộng/cao                       |
| `--line-len`      | 10       | tất cả      | đường lỗi dài tối thiểu, px                                |
| `--line-width`    | 2        | tất cả      | đường lỗi rộng tối đa, px                                  |

Thông số khai báo một chỗ trong `camera_checker/analysis_params.py` (bảng `SPEC`): thêm một dòng ở đó là tự có cờ dòng lệnh
và ô nhập trên web. File kết quả lưu cả thông số đã dùng (`params`); `compare` cảnh báo khi hai lần đo khác thông số.

## Giao diện web

```bash
.venv/bin/python -m camera_checker.web_app          # mở http://127.0.0.1:8000
.venv/bin/python -m camera_checker.web_app --lan    # cho máy khác trong mạng LAN truy cập
```

- Kéo thả cả thư mục ảnh vào trang: ảnh tự vào đúng ô theo tên file (`dark_01.png` -> ô Ảnh tối).
- Cột phải: điều kiện chụp và thông số phân tích. Ô khác mặc định được tô màu. Giá trị được trình duyệt ghi nhớ.
- `Ctrl+Enter` để phân tích; có thanh tiến trình tải ảnh.
- Kết quả: bật/tắt từng lớp đánh dấu, bấm vào điểm lỗi để phóng to từ ảnh gốc, lọc bảng theo kết quả/vùng/loại,
  tải `.json` (cùng định dạng với dòng lệnh) hoặc `.csv`.

### Thông tin điều kiện chụp

| Thông số    | Cách lấy                                                              |
|-------------|-----------------------------------------------------------------------|
| Độ phân giải| Tự nhận biết từ ảnh, ví dụ `3840x2160 (4K UHD)`                       |
| Camera      | Tự đọc từ EXIF (hãng + model)                                         |
| ISO         | Đọc từ EXIF nếu camera có ghi; `--iso` nhập tay được ưu tiên hơn      |
| Phơi sáng   | Đọc từ EXIF nếu có                                                    |
| Bitrate     | Chỉ nhập tay `--bitrate` (ảnh JPEG không chứa thông tin bitrate)      |

Camera GREMSY INFISIGHT không ghi ISO vào EXIF, nên cần nhập `--iso` tay.

### File kết quả `.json`

```json
{
 "info": {"resolution": "3840x2160", "resolution_name": "3840x2160 (4K UHD)", "frames": 5,
          "camera": "GREMSY INFISIGHT", "iso": 800, "iso_source": "nhập tay", "bitrate": "50Mbps",
          "serial": "SN-0012", "fps": 30, "tester": "Thang"},
 "params": {"t_dev": 40, "hit_pct": 100, "kernel": 9, "...": "..."},
 "summary": {"total": 0, "zoneA": 0, "single": 0, "cluster": 0, "line": 0},
 "defects": [{"x": 1920, "y": 1080, "zone": "A", "size": 1, "kind": "single"}]
}
```

- `zone`: `A` = vùng giữa (mặc định 1/2 khung hình ở giữa, chỉnh bằng `--zone-a-pct`), `B` = vùng rìa.
- `kind`: `single` = 1 px, `cluster` = cụm, `line` = đường mảnh dài ≥ 10 px.
- File kết quả kiểu cũ (chỉ có danh sách điểm lỗi) vẫn dùng được với `compare`.
