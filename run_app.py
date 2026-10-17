"""Điểm vào cho bản đóng gói (PyInstaller) và chạy nhanh: mở giao diện web kiểm tra pixel lỗi camera.
Dùng đường dẫn tuyệt đối tới package để PyInstaller phân tích được; tham số giống camera_checker.web_app (--port, --lan, --no-browser).
"""
from camera_checker.web_app import main

if __name__ == "__main__":
    main()
