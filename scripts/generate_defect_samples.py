"""Sinh bộ ảnh 4K giả lập có chủ đích gắn lỗi pixel để thử các test hot / dead / stuck / ir.

Chạy:  .venv/bin/python scripts/generate_defect_samples.py [-o samples/defects] [--frames 10]
Ra 4 thư mục con: hot/ dead/ stuck/ ir/ (mỗi bộ ảnh một thư mục, tránh trùng tên dark_01, white_01).
Lỗi gắn ở toạ độ cố định (xem DEFECTS) nên biết trước kết quả mong đợi; mỗi ảnh còn có nhiễu ngẫu nhiên
riêng từng frame để kiểm tra việc lọc nhiễu (pixel chỉ lỗi ở 1 frame không được tính là lỗi).
Ảnh lưu PNG (không nén mất dữ liệu) để lỗi không bị JPEG làm nhoè.
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

W, H = 3840, 2160
RNG = np.random.default_rng(42)

# (kind, x, y, w, h): kind chỉ để ghi chú; vùng A = khung giữa (960..2880, 540..1620)
SINGLES = [(1920, 1080), (1500, 900), (2400, 1300), (300, 200), (3500, 1900), (700, 1800)]
CLUSTERS = [(1200, 700, 3, 3), (3000, 400, 2, 2)]
LINES = [(2000, 1400, 1, 40), (500, 1000, 30, 1)]   # (x, y, w, h)


def stamp(img, value):
    """Gắn mọi lỗi cố định với giá trị `value` (số hoặc bộ BGR)."""
    for x, y in SINGLES:
        img[y, x] = value
    for x, y, w, h in CLUSTERS + LINES:
        img[y:y + h, x:x + w] = value


def noisy(base, sigma, ch=3):
    """Nền phẳng `base` + nhiễu Gauss, uint8."""
    shape = (H, W, ch) if ch > 1 else (H, W)
    img = np.full(shape, base, np.float32) + RNG.normal(0, sigma, shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def save(path, img):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    print("->", path)


def random_transients(img, value, n=60):
    """Pixel lỗi ngẫu nhiên chỉ có ở frame này: mô phỏng nhiễu, phải bị lọc khi dùng nhiều ảnh."""
    ys, xs = RNG.integers(10, H - 10, n), RNG.integers(10, W - 10, n)
    img[ys, xs] = value


def gen_stack(out, name, base, sigma, defect_value, transient_value, frames):
    for i in range(1, frames + 1):
        img = noisy(base, sigma)
        stamp(img, defect_value)
        random_transients(img, transient_value)
        save(out / f"{name}_{i:02d}.png", img)


def gen_stuck(out):
    """5 cảnh; pixel kẹt luôn ~100 ở mọi cảnh (lệch lân cận > 40 ở cả cảnh tối lẫn sáng)."""
    scenes = {"dark": (3, 3, 3), "white": (200, 200, 200),
              "red": (3, 3, 200), "green": (3, 200, 3), "blue": (200, 3, 3)}   # BGR
    for name, bgr in scenes.items():
        img = np.stack([noisy(b, 1.5, 1) for b in bgr], axis=-1)
        stamp(img, 100)
        save(out / f"{name}_01.png", img)


def gen_ir(out):
    """Camera nhiệt xám: t1 nền 80, t2 nền 140 (đáp ứng 60 DN); gắn 3 loại lỗi đáp ứng."""
    t1, t2 = noisy(80, 1.5, 1), noisy(140, 1.5, 1)
    kinds = {"stuck": (80, 80), "dead": (80, 95), "hot": (80, 240)}   # (giá trị ở t1, ở t2)
    pos = {"stuck": [(1920, 1080), (1000, 500)], "dead": [(2400, 1300), (800, 1700)], "hot": [(1500, 900), (3300, 1500)]}
    for k, pts in pos.items():
        for x, y in pts:
            t1[y, x], t2[y, x] = kinds[k]
    save(out / "t1_01.png", t1)
    save(out / "t2_01.png", t2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default="samples/defects", type=Path, help="thư mục ra (mặc định samples/defects)")
    ap.add_argument("--frames", type=int, default=10, help="số ảnh mỗi bộ hot/dead (mặc định 10)")
    a = ap.parse_args()
    gen_stack(a.out / "hot", "dark", base=2, sigma=1.0, defect_value=150, transient_value=150, frames=a.frames)
    gen_stack(a.out / "dead", "white", base=200, sigma=2.0, defect_value=15, transient_value=15, frames=a.frames)
    gen_stuck(a.out / "stuck")
    gen_ir(a.out / "ir")
    n = len(SINGLES) + len(CLUSTERS) + len(LINES)
    print(f"Xong. hot/dead mong đợi {n} lỗi cố định ({len(SINGLES)} single, {len(CLUSTERS)} cluster, {len(LINES)} line).")


if __name__ == "__main__":
    main()
