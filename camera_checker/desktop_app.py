"""Ứng dụng desktop: một cửa sổ riêng, không dùng trình duyệt.

Bộ phân tích chạy trong cùng tiến trình, phục vụ trên 127.0.0.1 (cổng ngẫu nhiên, chỉ cửa sổ này dùng) và được
hiển thị bằng pywebview: Windows = WebView2, macOS = WKWebView, Linux = Qt WebEngine (PyQt6, đóng gói kèm).
"""
import os
import socket
import sys
import threading

from werkzeug.serving import make_server

from . import web_app

TITLE = "Camera Checker - kiểm tra pixel lỗi"


def _silence_missing_streams():
    """Bản đóng gói không console (Windows) không có stdout/stderr: tránh lỗi khi in/ghi log."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port):
    server = make_server("127.0.0.1", port, web_app.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    _silence_missing_streams()
    server = _start_server(_free_port())
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True   # nút "Tải báo cáo PDF / .json / .csv" cần lưu file
        webview.create_window(TITLE, url, width=1360, height=900, min_size=(900, 600))
        webview.start(gui=os.environ.get("CAMERA_CHECKER_GUI") or None)   # ép backend khi cần: qt / gtk
    except Exception as e:   # thiếu WebView2 (Windows) hoặc không có màn hình
        sys.exit(f"ERROR: không mở được cửa sổ ứng dụng: {e}")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
