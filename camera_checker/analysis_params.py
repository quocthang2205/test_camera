"""Thông số thuật toán chỉnh được. Một bảng SPEC duy nhất sinh ra cờ dòng lệnh, form web và bước kiểm tra giá trị,
nên thêm thông số mới chỉ cần thêm một dòng ở đây rồi dùng `p.<key>` trong camera_checker/core.py.
"""
from types import SimpleNamespace

ALL = ("hot", "dead", "stuck", "ir")

# group: nhóm hiển thị trên web; modes: chế độ có dùng thông số này (web chỉ hiện thông số liên quan)
SPEC = [
    dict(key="t_dev", default=40, min=1, max=255, step=1, modes=("hot", "stuck"), group="Ngưỡng phát hiện",
         label="Ngưỡng lệch lân cận (DN)", help="pixel lệch khỏi median lân cận quá mức này bị tính là lỗi"),
    dict(key="dead_pct", default=50, min=1, max=99, step=1, modes=("dead",), group="Ngưỡng phát hiện",
         label="Ngưỡng pixel chết (% lân cận)", help="pixel tối hơn mức % này so với median lân cận bị tính là chết"),
    dict(key="hit_pct", default=100, min=1, max=100, step=1, modes=("hot", "dead"), group="Ngưỡng phát hiện",
         label="Tỉ lệ frame phải lỗi (%)", help="100 = lỗi ở mọi ảnh (lọc nhiễu tốt nhất); giảm để bắt pixel chập chờn"),
    dict(key="stuck_flat", default=10, min=1, max=255, step=1, modes=("stuck",), group="Ngưỡng phát hiện",
         label="Dao động tối đa giữa các cảnh (DN)", help="pixel kẹt: giá trị gần như không đổi giữa 5 cảnh"),
    dict(key="dark_max", default=50, min=0, max=255, step=1, modes=("hot",), group="Chặn nhầm bộ ảnh",
         label="Độ sáng tối đa của ảnh tối (DN)", help="median ảnh vượt mức này thì từ chối chạy test hot"),
    dict(key="white_min", default=50, min=0, max=255, step=1, modes=("dead",), group="Chặn nhầm bộ ảnh",
         label="Độ sáng tối thiểu của ảnh trắng (DN)", help="median ảnh thấp hơn mức này thì từ chối chạy test dead"),
    dict(key="ir_min_resp", default=20, min=0, max=255, step=1, modes=("ir",), group="Camera nhiệt",
         label="Đáp ứng tối thiểu t2−t1 (DN)", help="thấp hơn mức này coi như AGC đang bật, chuyển sang chế độ outlier"),
    dict(key="ir_dev", default=30, min=1, max=255, step=1, modes=("ir",), group="Camera nhiệt",
         label="Ngưỡng lệch lân cận IR (DN)", help="dùng cho pixel kẹt IR và chế độ outlier"),
    dict(key="ir_stuck_ratio", default=0.1, min=0.0, max=1.0, step=0.05, modes=("ir",), group="Camera nhiệt",
         label="Pixel kẹt: đáp ứng < x · median", help="pixel gần như không phản ứng với thay đổi nhiệt độ"),
    dict(key="ir_dead_ratio", default=0.5, min=0.0, max=1.0, step=0.05, modes=("ir",), group="Camera nhiệt",
         label="Pixel chết: đáp ứng < x · median", help="pixel phản ứng yếu hơn hẳn lân cận"),
    dict(key="ir_hot_ratio", default=1.5, min=1.0, max=10.0, step=0.1, modes=("ir",), group="Camera nhiệt",
         label="Pixel nóng: đáp ứng > x · median", help="pixel phản ứng mạnh hơn hẳn lân cận"),
    dict(key="kernel", default=9, min=3, max=31, step=2, modes=ALL, group="Hình học",
         label="Cửa sổ median (px, số lẻ)", help="kích thước vùng lân cận để so sánh; lớn hơn = bắt cụm lỗi to hơn"),
    dict(key="edge", default=4, min=0, max=200, step=1, modes=ALL, group="Hình học",
         label="Bỏ qua mép ảnh (px)", help="mép ảnh hay nhiễu do bộ lọc, không tính lỗi"),
    dict(key="zone_a_pct", default=50, min=10, max=100, step=5, modes=ALL, group="Hình học",
         label="Vùng giữa A (% chiều rộng/cao)", help="50 = khung giữa từ 1/4 đến 3/4 ảnh"),
    dict(key="line_len", default=10, min=2, max=10000, step=1, modes=ALL, group="Hình học",
         label="Đường lỗi: dài tối thiểu (px)", help="cụm mảnh và dài từ mức này trở lên được xếp loại đường (line)"),
    dict(key="line_width", default=2, min=1, max=50, step=1, modes=ALL, group="Hình học",
         label="Đường lỗi: rộng tối đa (px)", help="cụm rộng hơn mức này là cụm (cluster), không phải đường"),
]
BY_KEY = {s["key"]: s for s in SPEC}


class ParamError(ValueError):
    """Giá trị thông số không hợp lệ."""


def _cast(spec):
    return float if isinstance(spec["default"], float) else int


def defaults():
    return SimpleNamespace(**{s["key"]: s["default"] for s in SPEC})


def parse(raw):
    """raw: {key: chuỗi/số}; bỏ trống hoặc thiếu = mặc định. Kiểm tra kiểu và khoảng giá trị."""
    p = defaults()
    for key, val in (raw or {}).items():
        spec = BY_KEY.get(key)
        if spec is None or val is None or str(val).strip() == "":
            continue
        try:
            v = _cast(spec)(str(val).strip())
        except ValueError:
            raise ParamError(f"{spec['label']}: '{val}' không phải số{' nguyên' if _cast(spec) is int else ''}")
        if not spec["min"] <= v <= spec["max"]:
            raise ParamError(f"{spec['label']}: {v} nằm ngoài khoảng {spec['min']}–{spec['max']}")
        setattr(p, key, v)
    if p.kernel % 2 == 0:
        raise ParamError(f"cửa sổ median phải là số lẻ, nhận được {p.kernel}")
    return p


def changed(p):
    """Các thông số khác mặc định, để ghi chú vào kết quả."""
    return {s["key"]: getattr(p, s["key"]) for s in SPEC if getattr(p, s["key"]) != s["default"]}


def add_cli_args(parser, mode):
    """Thêm cờ --t-dev, --kernel ... (chỉ các thông số chế độ `mode` dùng) vào một subparser."""
    g = parser.add_argument_group("thông số phân tích (bỏ qua = mặc định)")
    for s in SPEC:
        if mode in s["modes"]:
            g.add_argument("--" + s["key"].replace("_", "-"), dest=s["key"], type=_cast(s), metavar="N",
                           help=f"{s['label']}: {s['help']} (mặc định {s['default']})")


def from_cli(args):
    return parse({s["key"]: getattr(args, s["key"], None) for s in SPEC})


def for_web():
    return [dict(s, modes=list(s["modes"])) for s in SPEC]
