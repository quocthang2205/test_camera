# Kiểm tra pixel lỗi camera

Phát hiện pixel nóng (hot), chết (dead), kẹt (stuck) và lỗi camera nhiệt (IR) từ bộ ảnh chụp cố định.
Mỗi kết quả kèm điều kiện chụp: độ phân giải (tự nhận biết), ISO, bitrate, tên camera.

## Cài đặt (một lần)

```bash
cd ~/test_camera
python3 -m venv .venv
.venv/bin/pip install numpy opencv-python-headless scipy flask
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

## Chạy bằng dòng lệnh

Luôn đặt pattern ảnh trong ngoặc kép.

```bash
# Pixel nóng: ảnh tối, ghi kèm ISO và bitrate
.venv/bin/python test_camera.py hot "dark_*.jpeg" --iso 800 --bitrate 50Mbps

# Pixel chết: ảnh nền trắng
.venv/bin/python test_camera.py dead "white_*.jpeg" --iso 100 --bitrate 50Mbps

# Pixel kẹt: 5 cảnh theo thứ tự dark white red green blue
.venv/bin/python test_camera.py stuck "dark_*.jpeg" "white_*.jpeg" "red_*.jpeg" "green_*.jpeg" "blue_*.jpeg"

# Camera nhiệt
.venv/bin/python test_camera.py ir "t1_*.png" "t2_*.png"

# Chọn số ảnh phân tích (hot/dead): -n 1 = kiểm nhanh 1 ảnh, mặc định 5 = chuẩn
.venv/bin/python test_camera.py hot "Test_1.jpeg" -n 1
.venv/bin/python test_camera.py hot "dark_*.jpeg" -n 3     # có 5 ảnh vẫn chỉ dùng 3 ảnh đầu theo tên

# Đặt tên file kết quả riêng cho từng lần đo (mặc định hot -> hot.json)
.venv/bin/python test_camera.py hot "dark_*.jpeg" --iso 800 -o hot_iso800

# So sánh 2 lần đo: điểm mới xuất hiện / biến mất; cảnh báo nếu khác độ phân giải, ISO, bitrate
.venv/bin/python test_camera.py compare hot_lan1.json hot_lan2.json
```

Về số ảnh: pixel chỉ bị tính là lỗi khi lỗi ở **tất cả** ảnh được phân tích. Dùng 5 ảnh sẽ lọc được nhiễu
ngẫu nhiên; dùng 1–4 ảnh thì chương trình in WARNING, chỉ nên dùng để kiểm nhanh, kết luận cuối cần 5 ảnh.

Xem đủ tuỳ chọn: `.venv/bin/python test_camera.py hot -h`

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
          "camera": "GREMSY INFISIGHT", "iso": 800, "iso_source": "nhập tay", "bitrate": "50Mbps"},
 "summary": {"total": 0, "zoneA": 0, "single": 0, "cluster": 0, "line": 0},
 "defects": [{"x": 1920, "y": 1080, "zone": "A", "size": 1, "kind": "single"}]
}
```

- `zone`: `A` = vùng giữa (1/2 khung hình ở giữa), `B` = vùng rìa.
- `kind`: `single` = 1 px, `cluster` = cụm, `line` = đường mảnh dài ≥ 10 px.
- File kết quả kiểu cũ (chỉ có danh sách điểm lỗi) vẫn dùng được với `compare`.

## Chạy bằng giao diện web

```bash
.venv/bin/python web_app.py           # tự mở http://127.0.0.1:8000
.venv/bin/python web_app.py --lan     # cho máy khác trong mạng LAN truy cập
```

1. Chọn tab loại test.
2. Kéo thả ảnh vào từng ô.
3. Với Pixel nóng / Pixel chết: chọn **Số ảnh phân tích** (1, 3 hoặc 5).
4. Nhập ISO (bỏ trống để đọc từ EXIF) và bitrate nếu có.
5. Bấm **Phân tích**, rồi tải file `.json` kết quả (đã có kèm điều kiện chụp).
