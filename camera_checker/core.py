# camera_checker/core.py  —  pip install numpy opencv-python scipy
# Phát hiện pixel lỗi (hot / dead / stuck / IR) từ chuỗi ảnh chụp cố định.
# LUÔN đặt pattern trong ngoặc kép: python -m camera_checker hot "dark_*.png"
# Ứng dụng desktop dùng chung lõi phân tích này: xem desktop_app.py / web_app.py
import argparse, glob, json, math, os, sys
import numpy as np, cv2
from scipy.ndimage import median_filter, label, find_objects
from . import analysis_params as params
from . import capture_info
from . import pdf_report

# Mọi ngưỡng chỉnh được nằm trong analysis_params.SPEC và đi vào các hàm dưới dạng `p`.
MIN_FRAMES = 5             # chuẩn: 5 ảnh mỗi bộ; ít hơn vẫn chạy được nhưng kém tin cậy
FRAME_MARKS = 2000         # số điểm tối đa lưu/vẽ cho mỗi ảnh khi xem từng ảnh (tổng vẫn đếm đủ)
COMPARE_TOL = 2            # compare: hai điểm cách nhau <= 2 px coi là cùng một điểm

# Mỗi chế độ: các bộ ảnh cần (theo thứ tự), đọc xám hay màu, số ảnh tối thiểu mỗi bộ.
# frames=True: chọn được số ảnh phân tích (1 ảnh kiểm nhanh, 5 ảnh chuẩn, 10 ảnh kỹ).
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


def med(img, k):
    """Median k x k lân cận. uint8 dùng cv2.medianBlur (nhanh); số âm/float dùng scipy."""
    if img.dtype == np.uint8:
        return cv2.medianBlur(img, k)
    return median_filter(img, size=k, mode="reflect")


def chans(fr): return [fr] if fr.ndim == 2 else [fr[..., c] for c in range(fr.shape[2])]


def trim(m, edge):
    if edge:
        m[:edge, :] = m[-edge:, :] = m[:, :edge] = m[:, -edge:] = False
    return m


def zone_box(W, H, p):
    """Khung vùng giữa A (x0, y0, x1, y1) theo % kích thước ảnh."""
    mx, my = W * (1 - p.zone_a_pct / 100) / 2, H * (1 - p.zone_a_pct / 100) / 2
    return mx, my, W - mx, H - my


def check_level(stack, mode, p):
    """Chặn chạy nhầm bộ ảnh: hot cần ảnh tối, dead cần ảnh nền trắng.
    Ảnh tối chạy dead sẽ biến nhiễu thành hàng trăm nghìn pixel chết giả."""
    level = float(np.median(stack[:, ::8, ::8]))   # lấy mẫu thưa cho nhanh với ảnh 4K
    if mode == "hot" and level > p.dark_max:
        die(f"ảnh quá sáng cho test hot (median {level:.0f} DN > {p.dark_max}): cần ảnh tối, che kín ống kính")
    if mode == "dead" and level < p.white_min:
        die(f"ảnh quá tối cho test dead (median {level:.0f} DN < {p.white_min}): cần ảnh nền trắng đều")
    return level


def pick_frames(stack, frames):
    """Lấy `frames` ảnh đầu của bộ (đã sắp theo tên) để phân tích."""
    if frames < 1:
        die(f"số ảnh phân tích phải >= 1, nhận được {frames}")
    if len(stack) < frames:
        die(f"chỉ có {len(stack)} ảnh, cần {frames}: thêm ảnh hoặc giảm số ảnh phân tích "
            "(dòng lệnh: -n; nếu đã đủ ảnh, kiểm tra ngoặc kép quanh pattern)")
    return stack[:frames]


def per_frame(stack, test, notes, p, frame_log=None):
    """Đếm số frame mỗi pixel bị flag; giữ pixel lỗi trong >= hit_pct % số frame.
    frame_log (list, tuỳ chọn): được thêm một dict cho mỗi ảnh gồm các điểm bị flag riêng ảnh đó;
    điểm trùng với lỗi cuối cùng có confirmed=True, còn lại là nhiễu bị loại."""
    n = len(stack)
    if n < MIN_FRAMES:   # 1 ảnh không lọc được nhiễu ngẫu nhiên, chỉ dùng để kiểm nhanh
        notes.append(f"WARNING: chỉ phân tích {n} ảnh (chuẩn {MIN_FRAMES}): nhiễu ngẫu nhiên có thể bị tính là lỗi, "
                     f"cần chạy lại với {MIN_FRAMES} ảnh trước khi kết luận")
    min_hits = max(1, math.ceil(p.hit_pct / 100 * n))
    hits = np.zeros(stack.shape[1:3], np.int32)
    masks = []
    for fr in stack:
        m = np.zeros(fr.shape[:2], bool)
        for ch in chans(fr):   # int16 tránh tràn uint8 khi cộng/so sánh
            m |= test(ch.astype(np.int16), med(ch, p.kernel).astype(np.int16))
        hits += m
        if frame_log is not None:
            masks.append(m)
    notes.append(f"{n} frame, ngưỡng {min_hits} frame")
    final = trim(hits >= min_hits, p.edge)
    if frame_log is not None:
        near = cv2.dilate(final.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0   # dung sai vài px quanh lỗi thật
        for m in masks:
            ds = find_defects(trim(m, p.edge), p)
            for d in ds:
                d["confirmed"] = bool(near[d["y"], d["x"]])
            frame_log.append(dict(total=len(ds), confirmed=sum(d["confirmed"] for d in ds), defects=ds[:FRAME_MARKS]))
    return final


def find_defects(mask, p):
    """Gom pixel lỗi thành cụm (8 lân cận); phân loại single/cluster/line và vùng A (giữa) / B."""
    H, W = mask.shape
    x0, y0, x1, y1 = zone_box(W, H, p)
    lab, _ = label(mask, structure=np.ones((3, 3)))
    out = []
    for i, sl in enumerate(find_objects(lab), start=1):   # chỉ xét bounding box từng cụm
        ys, xs = np.nonzero(lab[sl] == i)
        ys, xs = ys + sl[0].start, xs + sl[1].start
        cx, cy = xs.mean(), ys.mean()
        zone = "A" if x0 <= cx < x1 and y0 <= cy < y1 else "B"
        h, w = np.ptp(ys) + 1, np.ptp(xs) + 1
        if max(h, w) >= p.line_len and min(h, w) <= p.line_width:
            kind = "line"
        else:
            kind = "cluster" if len(xs) >= 2 else "single"
        out.append(dict(x=int(cx), y=int(cy), zone=zone, size=int(len(xs)), kind=kind))
    return out


def summarize(defects):
    count = lambda key, val: sum(d[key] == val for d in defects)
    return dict(total=len(defects), zoneA=count("zone", "A"), single=count("kind", "single"),
                cluster=count("kind", "cluster"), line=count("kind", "line"))


def detect_stuck(scenes, p):
    """Stuck: lệch lân cận ở mọi cảnh nhưng giá trị gần như không đổi giữa các cảnh."""
    sc = [s.mean(0) for s in scenes]
    if any(s.shape != sc[0].shape for s in sc):
        die("các cảnh dark/white/red/green/blue phải cùng kích thước")
    mask = np.zeros(sc[0].shape[:2], bool)
    for c in range(sc[0].shape[2]):
        ch = [s[..., c] for s in sc]
        dev = np.all([np.abs(x - med(to_u8(x), p.kernel)) > p.t_dev for x in ch], axis=0)
        flat = (np.max(ch, 0) - np.min(ch, 0)) < p.stuck_flat
        mask |= dev & flat
    return {"stuck": find_defects(trim(mask, p.edge), p)}


def detect_ir(s1, s2, notes, p):
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
    k, e = p.kernel, p.edge
    d1, d2 = np.abs(t1 - med(to_u8(t1), k)), np.abs(t2 - med(to_u8(t2), k))
    if m < p.ir_min_resp:           # AGC đang chuẩn hóa -> outlier mode
        notes.append(f"WARNING: response < {p.ir_min_resp} DN, AGC active -> outlier mode ({p.ir_dev} DN)")
        return {"ir_bad": find_defects(trim((d1 > p.ir_dev) & (d2 > p.ir_dev), e), p)}
    mr = med(resp, k)
    stuck = (np.abs(resp) < p.ir_stuck_ratio * mr) & (np.maximum(d1, d2) > p.ir_dev)
    return {"ir_stuck": find_defects(trim(stuck, e), p),
            "ir_dead": find_defects(trim((resp < p.ir_dead_ratio * mr) & ~stuck, e), p),
            "ir_hot": find_defects(trim(resp > p.ir_hot_ratio * mr, e), p)}


def analyze(mode, stacks, p=None, frame_log=None):
    """Chạy một chế độ trên các stack ảnh (đúng thứ tự MODES[mode]['slots']); p = analysis_params (None = mặc định).
    Trả về ({tên_kết_quả: [defect, ...]}, [ghi chú]).
    frame_log: list rỗng để nhận điểm bị flag của từng ảnh (chỉ hot/dead; xem per_frame)."""
    p = p or params.defaults()
    notes = []
    if mode in ("hot", "dead"):
        notes.append(f"median ảnh = {check_level(stacks[0], mode, p):.0f} DN")
    if mode == "hot":
        res = {"hot": find_defects(per_frame(stacks[0], lambda v, m: v > m + p.t_dev, notes, p, frame_log), p)}
    elif mode == "dead":
        res = {"dead": find_defects(per_frame(stacks[0], lambda v, m: v < p.dead_pct / 100 * m, notes, p, frame_log), p)}
    elif mode == "stuck":
        res = detect_stuck(stacks, p)
    elif mode == "ir":
        res = detect_ir(stacks[0], stacks[1], notes, p)
    else:
        die(f"chế độ không hợp lệ: {mode}")
    custom = {k: v for k, v in params.changed(p).items() if mode in params.BY_KEY[k]["modes"]}
    if custom:
        notes.append("thông số khác mặc định: " + ", ".join(f"{k}={v}" for k, v in custom.items()))
    return res, notes


def read_result(path):
    """Đọc file kết quả. Bản mới: {info, summary, defects}; bản cũ: chỉ list defects."""
    try:
        with open(path) as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as e:
        die(f"không đọc được file json '{path}': {e}")
    if isinstance(data, list):
        return data, {}, {}
    return data.get("defects", []), data.get("info", {}), data.get("params", {})


def run_compare(fa, fb, tol=COMPARE_TOL):
    """So 2 lần đo: điểm mới xuất hiện / biến mất (dung sai ±tol px)."""
    (a, ia, pa), (b, ib, pb) = read_result(fa), read_result(fb)
    for path, info in ((fa, ia), (fb, ib)):
        print(f"{path}: {capture_info.describe(info) if info else 'không có thông tin điều kiện chụp'}")
    # so sánh khác điều kiện chụp / khác thông số phân tích thì kết quả không đối chiếu được
    for what, A, B in (("điều kiện chụp", ia, ib), ("thông số", pa, pb)):
        keys = ("resolution", "iso", "exposure", "bitrate", "fps") if what == "điều kiện chụp" else A.keys()
        for key in keys:
            if A.get(key) is not None and B.get(key) is not None and A[key] != B[key]:
                print(f"WARNING: {what} {key} khác nhau ({A[key]} vs {B[key]}), kết quả so sánh có thể không chính xác")
    near = lambda d, L: any(abs(d["x"]-e["x"]) <= tol and abs(d["y"]-e["y"]) <= tol for e in L)
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
                           help=f"số ảnh phân tích, lấy theo thứ tự tên file: 1 = kiểm nhanh, {MIN_FRAMES} = chuẩn, 10 = kỹ "
                                f"(mặc định {MIN_FRAMES})")
        g = p.add_argument_group("điều kiện chụp (ghi vào kết quả; camera/ISO/phơi sáng nhập tay ưu tiên hơn EXIF)")
        for fld in capture_info.MANUAL_FIELDS:
            g.add_argument("--" + fld["key"], metavar="X", help=f"{fld['label']} ({fld['example']})")
        p.add_argument("--no-pdf", action="store_true", help="không sinh báo cáo PDF (mặc định sinh <out>.pdf)")
        params.add_cli_args(p, mode)
    p = sub.add_parser("compare", help="so 2 file kết quả json")
    p.add_argument("a"); p.add_argument("b")
    p.add_argument("--tol", type=int, default=COMPARE_TOL, help=f"dung sai vị trí, px (mặc định {COMPARE_TOL})")
    a = ap.parse_args()

    try:
        if a.mode == "compare":
            return run_compare(a.a, a.b, a.tol)
        cfg = MODES[a.mode]
        p = params.from_cli(a)
        manual = capture_info.clean_manual(vars(a))
        stacks = [load(getattr(a, s), cfg["gray"]) for s in cfg["slots"]]
        if cfg.get("frames"):
            stacks = [pick_frames(s, a.frames) for s in stacks]
        frame_log = []
        results, notes = analyze(a.mode, stacks, p, frame_log)
    except (PixelCheckError, ValueError) as e:   # ValueError: thông số / điều kiện chụp nhập sai
        sys.exit(f"ERROR: {e}")
    files = sorted(glob.glob(getattr(a, cfg["slots"][0])))[:len(stacks[0])]   # đúng các ảnh pick_frames đã lấy
    frames = [dict(name=os.path.basename(f), image=img, **log) for f, img, log in zip(files, stacks[0], frame_log)]
    with open(files[0], "rb") as fp:   # EXIF lấy từ ảnh đầu bộ thứ nhất
        info = capture_info.build_info(fp.read(65536), stacks[0].shape[1:], len(stacks[0]), manual)
    print(capture_info.describe(info))
    for note in notes:
        print(note)
    for key, defects in results.items():
        name = a.out + key[len(a.mode):]          # hot -> <out>, ir_stuck -> <out>_stuck
        s = summarize(defects)
        print(f"{name}: total={s['total']} zoneA={s['zoneA']} cluster={s['cluster']} line={s['line']}")
        with open(f"{name}.json", "w") as fp:
            json.dump(dict(info=info, params=vars(p), summary=s, defects=defects), fp, indent=1)
        print(f"-> {name}.json")
    if not a.no_pdf:
        H, W = stacks[0].shape[1:3]
        try:
            pdf = pdf_report.build_pdf(a.mode, info, vars(p), notes, list(results.items()), stacks[0][0],
                                       (W, H), zone_box(W, H, p), frames)
        except RuntimeError as e:   # thiếu font: vẫn giữ kết quả json, chỉ bỏ PDF
            return print(f"WARNING: không tạo được PDF: {e}")
        with open(f"{a.out}.pdf", "wb") as fp:
            fp.write(pdf)
        print(f"-> {a.out}.pdf")


if __name__ == "__main__":
    main()
