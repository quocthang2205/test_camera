"""Đóng gói thành một file chạy duy nhất cho hệ điều hành đang dùng (Linux / macOS / Windows) bằng PyInstaller.

Chạy:  python scripts/build_app.py        -> dist/camera-checker (Windows: dist/camera-checker.exe)
PyInstaller không build chéo hệ điều hành: muốn có đủ 3 bản thì chạy script này trên từng máy,
hoặc dùng workflow .github/workflows/build-app.yml (build cả 3 trên GitHub Actions).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "camera-checker"


def main():
    sep = os.pathsep   # PyInstaller: ';' trên Windows, ':' nơi khác
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--name", NAME,
        "--add-data", f"{ROOT / 'camera_checker' / 'web'}{sep}camera_checker/web",       # giao diện web
        "--add-data", f"{ROOT / 'camera_checker' / 'fonts'}{sep}camera_checker/fonts",   # font PDF có dấu tiếng Việt
        "--collect-submodules", "webview",   # cửa sổ GUI (pywebview chọn backend theo hệ điều hành lúc chạy)
        *(["--noconsole"] if sys.platform == "win32" else []),   # Windows: không hiện cửa sổ đen
        "--exclude-module", "tkinter", "--exclude-module", "matplotlib",
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
        str(ROOT / "run_app.py"),
    ]
    sys.exit(subprocess.call(cmd, cwd=ROOT))


if __name__ == "__main__":
    main()
