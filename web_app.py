"""Giao diện web cho test_camera: kéo-thả ảnh vào trình duyệt để kiểm tra pixel lỗi.

Chạy:  .venv/bin/python web_app.py          -> mở http://127.0.0.1:8000
       .venv/bin/python web_app.py --lan    -> cho máy khác trong mạng LAN truy cập
Phân tích dùng chung lõi với CLI (test_camera.analyze) nên kết quả giống hệt.
"""
import argparse, base64, threading, webbrowser
from pathlib import Path

import cv2
from flask import Flask, jsonify, request, send_from_directory

import capture_info
import test_camera as core

WEB_DIR = Path(__file__).parent / "web"
OVERLAY_MAX_W = 1600            # ảnh đánh dấu thu nhỏ cho nhẹ trình duyệt
# Màu theo thứ tự kết quả (hex cho giao diện, BGR cho OpenCV)
PALETTE = [("#ff3b30", (48, 59, 255)), ("#ff9f0a", (10, 159, 255)),
           ("#ffd60a", (10, 214, 255)), ("#30d158", (88, 209, 48))]

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024**3   # 2 GB: nhiều bộ ảnh 4K
app.json.sort_keys = False                        # giữ thứ tự tab hot/dead/stuck/ir


def render_overlay(img, groups):
    """Vẽ vòng tròn quanh từng điểm lỗi và khung vùng A lên ảnh thu nhỏ; trả về data URL JPEG."""
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    H, W = img.shape[:2]
    s = min(1.0, OVERLAY_MAX_W / W)
    if s < 1:
        img = cv2.resize(img, (round(W * s), round(H * s)), interpolation=cv2.INTER_AREA)
    cv2.rectangle(img, (round(W * s / 4), round(H * s / 4)), (round(3 * W * s / 4), round(3 * H * s / 4)),
                  (200, 200, 200), 1)
    for (_, bgr), defects in groups:
        for d in defects:
            cv2.circle(img, (round(d["x"] * s), round(d["y"] * s)), 14, bgr, 2)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/modes")
def modes():
    return jsonify(modes={m: dict(slots=c["slots"], min=c["min"], frames=bool(c.get("frames")), help=c["help"])
                          for m, c in core.MODES.items()},
                   hit_ratio=core.HIT_RATIO, default_frames=core.MIN_FRAMES)


@app.post("/api/analyze/<mode>")
def analyze(mode):
    cfg = core.MODES.get(mode)
    if cfg is None:
        return jsonify(error=f"chế độ không hợp lệ: {mode}"), 400
    try:
        stacks, first_blob = [], None
        for slot in cfg["slots"]:
            files = request.files.getlist(slot)
            if len(files) < cfg["min"]:
                core.die(f"bộ '{slot}' có {len(files)} ảnh, cần ít nhất {cfg['min']}")
            blobs = [f.read() for f in files]
            first_blob = first_blob or blobs[0]
            stacks.append(core.decode_images(blobs, [f.filename for f in files], cfg["gray"]))
        if cfg.get("frames"):
            frames = request.form.get("frames", str(core.MIN_FRAMES)).strip()
            if not frames.isdigit():
                core.die(f"số ảnh phân tích phải là số nguyên, nhận được '{frames}'")
            stacks = [core.pick_frames(s, int(frames)) for s in stacks]
        iso = request.form.get("iso", "").strip()
        if iso and not iso.isdigit():
            core.die(f"ISO phải là số nguyên, nhận được '{iso}'")
        results, notes = core.analyze(mode, stacks)
    except core.PixelCheckError as e:
        return jsonify(error=str(e)), 400
    info = capture_info.build_info(first_blob, stacks[0].shape[1:], len(stacks[0]),
                                   iso or None, request.form.get("bitrate"))

    groups = [(PALETTE[i % len(PALETTE)], defects) for i, defects in enumerate(results.values())]
    H, W = stacks[0].shape[1:3]
    return jsonify(
        notes=notes,
        info=info,
        info_text=capture_info.describe(info),
        size=dict(width=int(W), height=int(H)),
        results=[dict(name=name, color=color, summary=core.summarize(defects), defects=defects)
                 for (name, defects), ((color, _), _) in zip(results.items(), groups)],
        overlay=render_overlay(stacks[0][0], groups),
    )


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="tổng dung lượng ảnh vượt quá 2 GB"), 413


def main():
    ap = argparse.ArgumentParser(description="Web kiểm tra pixel lỗi camera")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--lan", action="store_true", help="mở cho máy khác trong mạng LAN (0.0.0.0)")
    ap.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    a = ap.parse_args()
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    if not a.no_browser:   # mở trình duyệt sau khi server kịp khởi động
        threading.Timer(1.0, webbrowser.open, [f"http://127.0.0.1:{a.port}"]).start()
    print(f"Mở trình duyệt: http://{'<IP-máy-này>' if a.lan else '127.0.0.1'}:{a.port}   (Ctrl+C để tắt)")
    app.run(host=host, port=a.port, threaded=True)


if __name__ == "__main__":
    main()
