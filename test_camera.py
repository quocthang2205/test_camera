# pixcheck.py  —  pip install numpy opencv-python scipy
# Phát hiện pixel lỗi (hot / dead / stuck / IR) từ chuỗi ảnh chụp cố định.
# LUÔN đặt pattern trong ngoặc kép: python test_camera.py hot "dark_*.png"
# Giao diện web dùng chung lõi phân tích này: xem web_app.py
import argparse, glob, json, math, sys
import numpy as np, cv2
from scipy.ndimage import median_filter, label, find_objects
import capture_info

T_DEV, EDGE = 40, 4        # DN lệch so với median lân cận; pixel bỏ mép
HIT_RATIO = 1.0            # pixel phải lỗi trong 100% số frame (5/5 ảnh)
MIN_FRAMES = 5             # chuẩn: 5 ảnh mỗi bộ; ít hơn vẫn chạy được nhưng kém tin cậy
LINE_LEN, LINE_WIDTH = 10, 2   # line = cụm mảnh (<=2 px) và dài (>=10 px) theo hàng/cột
DARK_MAX, WHITE_MIN = 50, 50   # median DN: ảnh tối phải <= 50, ảnh trắng phải >= 50 (chặn nhầm bộ ảnh)

# Mỗi chế độ: các bộ ảnh cần (theo thứ tự), đọc xám hay màu, số ảnh tối thiểu mỗi bộ.
# frames=True: chọn được số ảnh phân tích (1 ảnh để kiểm nhanh ... 5 ảnh chuẩn).
MODES = {
    "hot":   dict(slots=["dark"], gray=False, min=1, frames=True, help="pixel nóng từ ảnh tối (che ống kính)"),
    "dead":  dict(slots=["white"], gray=False, min=1, frames=True, help="pixel chết từ ảnh nền trắng đều"),
    "stuck": dict(slots=["dark", "white", "red", "green", "blue"], gray=False, min=1, help="pixel kẹt từ 5 cảnh"),
    "ir":    dict(slots=["t1", "t2"], gray=True, min=1, help="camera nhiệt, 2 mức nhiệt độ"),
}


class PixelCheckError(ValueError):
    """Lỗi đầu vào: CLI in ra rồi thoát, web trả về cho người dùng."""


def die(msg):
    raise PixelCheckError(msg)


def stack_images(imgs, names):
    """Gộp ảnh đã đọc thành stack uint8; kiểm tra rỗng, file hỏng, lệch kích thước."""
    if not imgs:
        die("không có ảnh nào")
    for im, n in zip(imgs, names):
        if im is None:
            die(f"không đọc được ảnh '{n}'")
        if im.shape != imgs[0].shape:
            die(f"'{n}' có kích thước {im.shape}, khác {imgs[0].shape} của '{names[0]}'")
    return np.stack(imgs)


def read_flag(gray):
    return cv2.IMREAD_GRAYSCALE if gray else cv2.IMREAD_COLOR


def load(pat, gray=False):
    """Đọc mọi ảnh khớp pattern trên đĩa."""
    files = sorted(glob.glob(pat))
    if not files:
        die(f"không có ảnh nào khớp '{pat}' (nhớ đặt pattern trong ngoặc kép)")
    return stack_images([cv2.imread(f, read_flag(gray)) for f in files], files)


def decode_images(blobs, names, gray=False):
    """Giải mã ảnh từ bytes (file upload)."""
    imgs = [cv2.imdecode(np.frombuffer(b, np.uint8), read_flag(gray)) for b in blobs]
    return stack_images(imgs, names)


def to_u8(img):
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)


def med(img):
    """Median 9x9 lân cận. uint8 dùng cv2.medianBlur (nhanh); số âm/float dùng scipy."""
    if img.dtype == np.uint8:
        return cv2.medianBlur(img, 9)
    return median_filter(img, size=9, mode="reflect")


def chans(fr): return [fr] if fr.ndim == 2 else [fr[..., c] for c in range(fr.shape[2])]


def trim(m):
    m[:EDGE, :] = m[-EDGE:, :] = m[:, :EDGE] = m[:, -EDGE:] = False
    return m


def check_level(stack, mode):
    """Chặn chạy nhầm bộ ảnh: hot cần ảnh tối, dead cần ảnh nền trắng.
    Ảnh tối chạy dead sẽ biến nhiễu thành hàng trăm nghìn pixel chết giả."""
    level = float(np.median(stack[:, ::8, ::8]))   # lấy mẫu thưa cho nhanh với ảnh 4K
    if mode == "hot" and level > DARK_MAX:
        die(f"ảnh quá sáng cho test hot (median {level:.0f} DN > {DARK_MAX}): cần ảnh tối, che kín ống kính")
    if mode == "dead" and level < WHITE_MIN:
        die(f"ảnh quá tối cho test dead (median {level:.0f} DN < {WHITE_MIN}): cần ảnh nền trắng đều")
    return level


def pick_frames(stack, frames):
    """Lấy `frames` ảnh đầu của bộ (đã sắp theo tên) để phân tích."""
    if frames < 1:
        die(f"số ảnh phân tích phải >= 1, nhận được {frames}")
    if len(stack) < frames:
        die(f"chỉ có {len(stack)} ảnh, cần {frames}: thêm ảnh hoặc giảm số ảnh phân tích "
            "(dòng lệnh: -n; nếu đã đủ ảnh, kiểm tra ngoặc kép quanh pattern)")
    return stack[:frames]


def per_frame(stack, test, notes):
    """Đếm số frame mỗi pixel bị flag; giữ pixel lỗi trong >= HIT_RATIO số frame."""
    n = len(stack)
    if n < MIN_FRAMES:   # 1 ảnh không lọc được nhiễu ngẫu nhiên, chỉ dùng để kiểm nhanh
        notes.append(f"WARNING: chỉ phân tích {n} ảnh (chuẩn {MIN_FRAMES}): nhiễu ngẫu nhiên có thể bị tính là lỗi, "
                     f"cần chạy lại với {MIN_FRAMES} ảnh trước khi kết luận")
    min_hits = math.ceil(HIT_RATIO * n)
    hits = np.zeros(stack.shape[1:3], np.int32)
    for fr in stack:
        m = np.zeros(fr.shape[:2], bool)
        for ch in chans(fr):   # int16 tránh tràn uint8 khi cộng/so sánh
            m |= test(ch.astype(np.int16), med(ch).astype(np.int16))
        hits += m
    notes.append(f"{n} frame, ngưỡng {min_hits} frame")
    return trim(hits >= min_hits)


def find_defects(mask):
    """Gom pixel lỗi thành cụm (8 lân cận); phân loại single/cluster/line và vùng A (giữa) / B."""
    H, W = mask.shape
    lab, _ = label(mask, structure=np.ones((3, 3)))
    out = []
    for i, sl in enumerate(find_objects(lab), start=1):   # chỉ xét bounding box từng cụm
        ys, xs = np.nonzero(lab[sl] == i)
        ys, xs = ys + sl[0].start, xs + sl[1].start
        cx, cy = xs.mean(), ys.mean()
        zone = "A" if W/4 <= cx < 3*W/4 and H/4 <= cy < 3*H/4 else "B"
        h, w = np.ptp(ys) + 1, np.ptp(xs) + 1
        if max(h, w) >= LINE_LEN and min(h, w) <= LINE_WIDTH:
            kind = "line"
        else:
            kind = "cluster" if len(xs) >= 2 else "single"
        out.append(dict(x=int(cx), y=int(cy), zone=zone, size=int(len(xs)), kind=kind))
    return out


def summarize(defects):
    count = lambda key, val: sum(d[key] == val for d in defects)
    return dict(total=len(defects), zoneA=count("zone", "A"), single=count("kind", "single"),
                cluster=count("kind", "cluster"), line=count("kind", "line"))


def detect_stuck(scenes):
    """Stuck: lệch lân cận ở mọi cảnh nhưng giá trị gần như không đổi giữa các cảnh."""
    sc = [s.mean(0) for s in scenes]
    if any(s.shape != sc[0].shape for s in sc):
        die("các cảnh dark/white/red/green/blue phải cùng kích thước")
    mask = np.zeros(sc[0].shape[:2], bool)
    for c in range(sc[0].shape[2]):
        ch = [s[..., c] for s in sc]
        dev = np.all([np.abs(x - med(to_u8(x))) > T_DEV for x in ch], axis=0)
        flat = (np.max(ch, 0) - np.min(ch, 0)) < 10
        mask |= dev & flat
    return {"stuck": find_defects(trim(mask))}


def detect_ir(s1, s2, notes):
    """IR: so đáp ứng giữa 2 mức nhiệt; tự xử lý khi t2 lạnh hơn t1."""
    t1, t2 = s1.mean(0), s2.mean(0)
    if t1.shape != t2.shape:
        die("ảnh t1 và t2 phải cùng kích thước")
    resp = t2 - t1
    m = np.median(resp)
    notes.append(f"median response = {m:.1f} DN")
    if m < 0:                       # t2 lạnh hơn t1 -> đổi dấu để logic bên dưới vẫn đúng
        notes.append("NOTE: t2 lạnh hơn t1, dùng |response|")
        resp, m = -resp, -m
    d1, d2 = np.abs(t1 - med(to_u8(t1))), np.abs(t2 - med(to_u8(t2)))
    if m < 20:                      # AGC đang chuẩn hóa -> outlier mode
        notes.append("WARNING: response < 20 DN, AGC active -> outlier mode (30 DN)")
        return {"ir_bad": find_defects(trim((d1 > 30) & (d2 > 30)))}
    mr = med(resp)
    stuck = (np.abs(resp) < 0.1 * mr) & (np.maximum(d1, d2) > 30)
    return {"ir_stuck": find_defects(trim(stuck)),
            "ir_dead": find_defects(trim((resp < 0.5 * mr) & ~stuck)),
            "ir_hot": find_defects(trim(resp > 1.5 * mr))}


def analyze(mode, stacks):
    """Chạy một chế độ trên các stack ảnh (đúng thứ tự MODES[mode]['slots']).
    Trả về ({tên_kết_quả: [defect, ...]}, [ghi chú])."""
    notes = []
    if mode in ("hot", "dead"):
        notes.append(f"median ảnh = {check_level(stacks[0], mode):.0f} DN")
    if mode == "hot":
        res = {"hot": find_defects(per_frame(stacks[0], lambda v, m: v > m + T_DEV, notes))}
    elif mode == "dead":
        res = {"dead": find_defects(per_frame(stacks[0], lambda v, m: v < 0.5 * m, notes))}
    elif mode == "stuck":
        res = detect_stuck(stacks)
    elif mode == "ir":
        res = detect_ir(stacks[0], stacks[1], notes)
    else:
        die(f"chế độ không hợp lệ: {mode}")
    return res, notes


def read_result(path):
    """Đọc file kết quả. Bản mới: {info, summary, defects}; bản cũ: chỉ list defects."""
    try:
        with open(path) as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as e:
        die(f"không đọc được file json '{path}': {e}")
    return (data, {}) if isinstance(data, list) else (data.get("defects", []), data.get("info", {}))


def run_compare(fa, fb):
    """So 2 lần đo: điểm mới xuất hiện / biến mất (dung sai ±2 px)."""
    (a, ia), (b, ib) = read_result(fa), read_result(fb)
    for path, info in ((fa, ia), (fb, ib)):
        print(f"{path}: {capture_info.describe(info) if info else 'không có thông tin điều kiện chụp'}")
    for key in ("resolution", "iso", "bitrate"):   # so sánh khác điều kiện thì kết quả không đối chiếu được
        if ia.get(key) and ib.get(key) and ia[key] != ib[key]:
            print(f"WARNING: {key} khác nhau ({ia[key]} vs {ib[key]}), kết quả so sánh có thể không chính xác")
    near = lambda d, L: any(abs(d["x"]-e["x"]) <= 2 and abs(d["y"]-e["y"]) <= 2 for e in L)
    new = [d for d in b if not near(d, a)]
    gone = [d for d in a if not near(d, b)]
    print(f"new={len(new)} (zoneA={sum(d['zone']=='A' for d in new)}) gone={len(gone)}")
    for tag, L in (("NEW", new), ("GONE", gone)):
        for d in L:
            print(f"  {tag:4} x={d['x']} y={d['y']} zone={d['zone']} kind={d['kind']} size={d['size']}")


def main():
    ap = argparse.ArgumentParser(description="Kiểm tra pixel lỗi camera. Pattern phải đặt trong ngoặc kép.")
    sub = ap.add_subparsers(dest="mode", required=True)
    for mode, cfg in MODES.items():
        p = sub.add_parser(mode, help=cfg["help"])
        for slot in cfg["slots"]:
            p.add_argument(slot, help=f"pattern ảnh {slot}, ví dụ \"{slot}_*.png\"")
        p.add_argument("-o", "--out", default=mode, help=f"tên file kết quả (mặc định {mode} -> {mode}.json)")
        if cfg.get("frames"):
            p.add_argument("-n", "--frames", type=int, default=MIN_FRAMES,
                           help=f"số ảnh phân tích, lấy theo thứ tự tên file: 1 = kiểm nhanh, {MIN_FRAMES} = chuẩn "
                                f"(mặc định {MIN_FRAMES})")
        p.add_argument("--iso", type=int, help="ISO lúc chụp (ưu tiên hơn ISO đọc từ EXIF)")
        p.add_argument("--bitrate", help="bitrate luồng video, ví dụ \"50Mbps\" (ảnh không chứa thông tin này)")
    p = sub.add_parser("compare", help="so 2 file kết quả json")
    p.add_argument("a"); p.add_argument("b")
    a = ap.parse_args()

    try:
        if a.mode == "compare":
            return run_compare(a.a, a.b)
        cfg = MODES[a.mode]
        stacks = [load(getattr(a, s), cfg["gray"]) for s in cfg["slots"]]
        if cfg.get("frames"):
            stacks = [pick_frames(s, a.frames) for s in stacks]
        results, notes = analyze(a.mode, stacks)
    except PixelCheckError as e:
        sys.exit(f"ERROR: {e}")
    with open(sorted(glob.glob(getattr(a, cfg["slots"][0])))[0], "rb") as fp:   # EXIF lấy từ ảnh đầu bộ thứ nhất
        info = capture_info.build_info(fp.read(65536), stacks[0].shape[1:], len(stacks[0]), a.iso, a.bitrate)
    print(capture_info.describe(info))
    for note in notes:
        print(note)
    for key, defects in results.items():
        name = a.out + key[len(a.mode):]          # hot -> <out>, ir_stuck -> <out>_stuck
        s = summarize(defects)
        print(f"{name}: total={s['total']} zoneA={s['zoneA']} cluster={s['cluster']} line={s['line']}")
        with open(f"{name}.json", "w") as fp:
            json.dump(dict(info=info, summary=s, defects=defects), fp, indent=1)
        print(f"-> {name}.json")


if __name__ == "__main__":
    main()
