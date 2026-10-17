"""Điều kiện chụp của bộ ảnh test: độ phân giải (tự nhận biết), ISO, bitrate, camera.

- Độ phân giải lấy từ kích thước ảnh thật, không cần nhập.
- ISO / thời gian phơi sáng / hãng-model đọc từ EXIF nếu camera có ghi.
  ISO nhập tay (--iso) được ưu tiên hơn EXIF.
- Bitrate là thông số của luồng video, ảnh JPEG không chứa -> chỉ nhập tay.
- Các trường nhập tay khác (serial, firmware, FPS, nhiệt độ, người test, ghi chú) khai báo trong MANUAL_FIELDS;
  camera / phơi sáng nhập tay ghi đè giá trị đọc từ EXIF.
Bộ đọc EXIF viết thuần Python, không cần cài thêm thư viện.
"""
import struct

# Tên gọi quen thuộc của các độ phân giải hay gặp
RES_NAMES = {
    (7680, 4320): "8K UHD", (4096, 2160): "DCI 4K", (3840, 2160): "4K UHD",
    (2560, 1440): "QHD 1440p", (1920, 1080): "Full HD 1080p", (1280, 720): "HD 720p",
    (640, 512): "640x512 (nhiệt)", (640, 480): "VGA", (384, 288): "384x288 (nhiệt)",
}

TAG_MAKE, TAG_MODEL, TAG_EXIF_IFD = 0x010F, 0x0110, 0x8769
TAG_EXPOSURE, TAG_ISO = 0x829A, 0x8827
TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}

# Trường nhập tay: key, nhãn, ví dụ, kiểu. Thứ tự này là thứ tự hiển thị trên web / dòng mô tả.
MANUAL_FIELDS = [
    dict(key="camera", label="Camera", example="tự đọc EXIF", kind="text"),
    dict(key="serial", label="Số serial", example="vd: SN-000123", kind="text"),
    dict(key="firmware", label="Firmware", example="vd: v1.2.3", kind="text"),
    dict(key="iso", label="ISO", example="tự đọc EXIF", kind="int"),
    dict(key="exposure", label="Phơi sáng", example="vd: 1/60 s", kind="text"),
    dict(key="bitrate", label="Bitrate", example="vd: 50Mbps", kind="text"),
    dict(key="fps", label="FPS", example="vd: 30", kind="number"),
    dict(key="temperature", label="Nhiệt độ môi trường", example="vd: 25°C", kind="text"),
    dict(key="tester", label="Người test", example="vd: Thắng", kind="text"),
    dict(key="note", label="Ghi chú", example="vd: lần đo sau burn-in 24h", kind="text"),
]
MAX_TEXT = 200


def resolution_label(width, height):
    name = RES_NAMES.get((width, height))
    return f"{width}x{height}" + (f" ({name})" if name else "")


def _read_ifd(tiff, offset, end):
    """Đọc một IFD của khối TIFF; trả về {tag: giá trị} cho các kiểu ASCII/SHORT/LONG/RATIONAL."""
    count = struct.unpack_from(end + "H", tiff, offset)[0]
    tags = {}
    for i in range(count):
        tag, typ, n, raw = struct.unpack_from(end + "HHI4s", tiff, offset + 2 + 12 * i)
        size = TYPE_SIZE.get(typ, 1) * n
        data = raw[:size] if size <= 4 else tiff[struct.unpack(end + "I", raw)[0]:][:size]
        if n == 0 or len(data) < size:   # tag rỗng / trỏ ra ngoài khối EXIF (firmware ghi lỗi): bỏ qua tag đó
            continue
        if typ == 2:
            tags[tag] = data.split(b"\0")[0].decode("ascii", "ignore").strip()
        elif typ == 3:
            tags[tag] = struct.unpack_from(end + "H", data)[0]
        elif typ == 4:
            tags[tag] = struct.unpack_from(end + "I", data)[0]
        elif typ == 5:
            num, den = struct.unpack_from(end + "II", data)
            tags[tag] = num / den if den else None
    return tags


def read_exif(blob):
    """Lấy Make/Model/ISO/thời gian phơi sáng từ EXIF của JPEG. Ảnh không có EXIF -> {}."""
    try:
        i = blob.find(b"Exif\0\0", 0, 65536)
        if i < 0:
            return {}
        tiff = blob[i + 6:]
        end = "<" if tiff[:2] == b"II" else ">"
        ifd0 = _read_ifd(tiff, struct.unpack_from(end + "I", tiff, 4)[0], end)
        exif = _read_ifd(tiff, ifd0[TAG_EXIF_IFD], end) if TAG_EXIF_IFD in ifd0 else {}
    except (struct.error, IndexError, KeyError, ValueError):
        return {}   # EXIF hỏng/thiếu: bỏ qua, không làm hỏng phép phân tích
    out = {}
    camera = " ".join(v for v in (ifd0.get(TAG_MAKE), ifd0.get(TAG_MODEL)) if v)
    if camera:
        out["camera"] = camera
    if exif.get(TAG_ISO):
        out["iso"] = exif[TAG_ISO]
    if exif.get(TAG_EXPOSURE):
        t = exif[TAG_EXPOSURE]
        out["exposure"] = f"1/{round(1 / t)} s" if t < 1 else f"{t:g} s"
    return out


def clean_manual(raw):
    """Chuẩn hoá các trường nhập tay; bỏ trống thì bỏ qua. Sai kiểu -> ValueError."""
    out = {}
    for f in MANUAL_FIELDS:
        val = str(raw.get(f["key"]) or "").strip()[:MAX_TEXT]
        if not val:
            continue
        if f["kind"] == "int":
            if not val.isdigit():
                raise ValueError(f"{f['label']} phải là số nguyên, nhận được '{val}'")
            val = int(val)
        elif f["kind"] == "number":
            try:
                val = float(val)
            except ValueError:
                raise ValueError(f"{f['label']} phải là số, nhận được '{val}'")
            val = int(val) if val.is_integer() else val
        out[f["key"]] = val
    return out


def build_info(first_blob, shape, frames, manual=None):
    """Gom điều kiện chụp của một bộ ảnh. shape = (H, W[, C]); manual = kết quả clean_manual()."""
    height, width = shape[:2]
    exif, manual = read_exif(first_blob), manual or {}
    info = dict(resolution=f"{width}x{height}", resolution_name=resolution_label(width, height), frames=frames)
    for key in ("camera", "exposure"):   # nhập tay ghi đè EXIF
        if manual.get(key) or exif.get(key):
            info[key] = manual.get(key) or exif[key]
    if "iso" in manual:
        info["iso"], info["iso_source"] = manual["iso"], "nhập tay"
    elif "iso" in exif:
        info["iso"], info["iso_source"] = exif["iso"], "EXIF"
    for f in MANUAL_FIELDS:
        if f["key"] not in info and f["key"] in manual:
            info[f["key"]] = manual[f["key"]]
    return info


def describe(info):
    """Một dòng mô tả để in ra màn hình / ghi biên bản."""
    parts = [f"độ phân giải {info['resolution_name']}", f"{info['frames']} ảnh"]
    if "camera" in info:
        parts.insert(0, info["camera"])
    for key, fmt in (("serial", "SN {}"), ("firmware", "FW {}")):
        if key in info:
            parts.append(fmt.format(info[key]))
    parts.append(f"ISO {info['iso']} ({info['iso_source']})" if "iso" in info else "ISO: chưa có (dùng --iso)")
    if "exposure" in info:
        parts.append(f"phơi sáng {info['exposure']}")
    parts.append(f"bitrate {info['bitrate']}" if "bitrate" in info else "bitrate: chưa nhập (dùng --bitrate)")
    for key, fmt in (("fps", "{} fps"), ("temperature", "nhiệt độ {}"), ("tester", "người test {}"), ("note", "ghi chú: {}")):
        if key in info:
            parts.append(fmt.format(info[key]))
    return " · ".join(parts)
