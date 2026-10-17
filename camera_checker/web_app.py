"""Giao diện web cho camera_checker: kéo-thả ảnh vào trình duyệt để kiểm tra pixel lỗi.

Chạy:  .venv/bin/python -m camera_checker.web_app          -> mở http://127.0.0.1:8000
       .venv/bin/python -m camera_checker.web_app --lan    -> cho máy khác trong mạng LAN truy cập
Phân tích dùng chung lõi với CLI (core.analyze) nên kết quả giống hệt.
"""
import argparse, base64, io, threading, webbrowser
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_file, send_from_directory

from . import analysis_params as params
from . import capture_info
from . import pdf_report
from . import core

WEB_DIR = Path(__file__).parent / "web"
PREVIEW_MAX_W = 1600            # ảnh nền thu nhỏ cho nhẹ trình duyệt; điểm lỗi do trình duyệt vẽ đè (SVG)
PALETTE = pdf_report.PALETTE

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024**3   # 2 GB: nhiều bộ ảnh 4K
app.json.sort_keys = False                        # giữ thứ tự tab hot/dead/stuck/ir


def render_preview(img):
    """Ảnh đầu tiên thu nhỏ (chưa đánh dấu) dạng data URL JPEG."""
    H, W = img.shape[:2]
    if W > PREVIEW_MAX_W:
        img = cv2.resize(img, (PREVIEW_MAX_W, round(H * PREVIEW_MAX_W / W)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/static/<path:name>")
def static_file(name):
    return send_from_directory(WEB_DIR, name)


@app.get("/api/config")
def config():
    """Mọi thứ giao diện cần để tự dựng form: chế độ, trường điều kiện chụp, thông số phân tích."""
    return jsonify(modes={m: dict(slots=c["slots"], min=c["min"], frames=bool(c.get("frames")), help=c["help"])
                          for m, c in core.MODES.items()},
                   default_frames=core.MIN_FRAMES, fields=capture_info.MANUAL_FIELDS, params=params.for_web())


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
        manual = capture_info.clean_manual(request.form)
        p = params.parse({s["key"]: request.form.get("p_" + s["key"]) for s in params.SPEC})
        results, notes = core.analyze(mode, stacks, p)
    except ValueError as e:   # PixelCheckError / ParamError / trường nhập tay sai kiểu
        return jsonify(error=str(e)), 400
    info = capture_info.build_info(first_blob, stacks[0].shape[1:], len(stacks[0]), manual)

    H, W = stacks[0].shape[1:3]
    return jsonify(
        mode=mode,
        notes=notes,
        info=info,
        info_text=capture_info.describe(info),
        params=vars(p),
        size=dict(width=int(W), height=int(H)),
        zone=core.zone_box(W, H, p),
        results=[dict(name=name, color=PALETTE[i % len(PALETTE)], summary=core.summarize(defects), defects=defects)
                 for i, (name, defects) in enumerate(results.items())],
        preview=render_preview(stacks[0][0]),
    )


@app.post("/api/report")
def report():
    """Sinh PDF từ kết quả mà /api/analyze vừa trả về (trình duyệt gửi lại nguyên JSON đó).
    Không lưu ảnh trên server: ảnh đánh dấu vẽ lại từ ảnh preview có sẵn trong kết quả."""
    data = request.get_json(silent=True) or {}
    try:
        head, b64 = str(data.get("preview", "")).split(",", 1)
        if not head.startswith("data:image/"):
            raise ValueError
        img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError
        size = (int(data["size"]["width"]), int(data["size"]["height"]))
        results = [(str(r["name"]), list(r["defects"])) for r in data["results"]]
        pdf = pdf_report.build_pdf(str(data["mode"]), dict(data["info"]), dict(data["params"]),
                                   [str(n) for n in data.get("notes", [])], results, img, size,
                                   [float(v) for v in data["zone"]])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="dữ liệu kết quả không hợp lệ, hãy phân tích lại"), 400
    except RuntimeError as e:   # thiếu font
        return jsonify(error=str(e)), 500
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name=f"{data['mode']}_report.pdf")


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
