"""Sinh báo cáo PDF cho một lần kiểm tra: điều kiện chụp, tổng hợp, ảnh đánh dấu vị trí lỗi, thông số, danh sách điểm.
Dùng chung cho dòng lệnh (core.py) và web (web_app.py). Cần font TTF có dấu tiếng Việt (DejaVu / Noto / Arial).
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path

import cv2
from fpdf import FPDF
from fpdf.fonts import FontFace

from . import analysis_params as params

PALETTE = ["#ff3b30", "#ff9f0a", "#ffd60a", "#30d158"]   # màu theo thứ tự kết quả, giống giao diện web
MODE_NAMES = {"hot": "Pixel nóng", "dead": "Pixel chết", "stuck": "Pixel kẹt", "ir": "Camera nhiệt"}
RESULT_NAMES = {"hot": "Pixel nóng", "dead": "Pixel chết", "stuck": "Pixel kẹt", "ir_stuck": "IR kẹt",
                "ir_dead": "IR chết", "ir_hot": "IR nóng", "ir_bad": "IR lỗi (outlier)"}
KIND_VI = {"single": "đơn", "cluster": "cụm", "line": "đường"}
INFO_ROWS = [("camera", "Camera"), ("serial", "Số serial"), ("firmware", "Firmware"),
             ("resolution_name", "Độ phân giải"), ("frames", "Số ảnh phân tích"), ("iso", "ISO"),
             ("exposure", "Phơi sáng"), ("bitrate", "Bitrate"), ("fps", "FPS"),
             ("temperature", "Nhiệt độ môi trường"), ("tester", "Người test"), ("note", "Ghi chú")]
MAX_ROWS = 300            # danh sách điểm lỗi trong PDF; đầy đủ nằm ở file .json / .csv
IMAGE_MAX_W = 1600        # ảnh đánh dấu thu nhỏ cho PDF nhẹ
# (thường, đậm): Linux DejaVu / Noto, Windows Arial, macOS Arial
FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]
INK, MUTED, LINE, ACCENT = (28, 28, 30), (110, 110, 115), (220, 220, 214), (10, 100, 214)


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def mark_image(img, size, results, zone):
    """Thu nhỏ ảnh, vẽ khung vùng A và vòng tròn quanh từng điểm lỗi. size = (W, H) ảnh gốc
    (ảnh truyền vào có thể đã thu nhỏ sẵn, như ảnh preview của web). Trả về bytes JPEG."""
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    if img.shape[1] > IMAGE_MAX_W:
        img = cv2.resize(img, (IMAGE_MAX_W, round(img.shape[0] * IMAGE_MAX_W / img.shape[1])), interpolation=cv2.INTER_AREA)
    s = img.shape[1] / size[0]
    x0, y0, x1, y1 = (round(v * s) for v in zone)
    cv2.rectangle(img, (x0, y0), (x1, y1), (200, 200, 200), 2)
    for i, (_, defects) in enumerate(results):
        r, g, b = _hex(PALETTE[i % len(PALETTE)])
        for d in defects:
            cv2.circle(img, (round(d["x"] * s), round(d["y"] * s)), 14, (b, g, r), 3)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


class _Report(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("main", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"Báo cáo kiểm tra pixel lỗi camera · trang {self.page_no()}/{{nb}}", align="C")


def _font(pdf):
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdf.add_font("main", "", regular)
            pdf.add_font("main", "B", bold)
            return
    raise RuntimeError("không tìm thấy font TTF có dấu tiếng Việt (cài fonts-dejavu-core hoặc sửa FONT_CANDIDATES)")


def _heading(pdf, text):
    pdf.ln(4)
    pdf.set_font("main", "B", 12)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)
    pdf.set_text_color(*INK)
    pdf.set_font("main", size=9.5)


def _table(pdf, header, rows, widths, align=None):
    head = FontFace(emphasis="BOLD", fill_color=(240, 240, 236))
    with pdf.table(col_widths=widths, headings_style=head, line_height=5.6, text_align=align or "LEFT",
                   borders_layout="HORIZONTAL_LINES", padding=1.2) as t:
        for row in [header, *rows]:
            r = t.row()
            for cell in row:
                r.cell(str(cell))


def build_pdf(mode, info, used_params, notes, results, image, size, zone):
    """results: [(tên, [defect, ...]), ...] đúng thứ tự màu. image: ảnh đầu tiên của bộ thứ nhất (BGR/xám).
    used_params: dict thông số đã dùng. Trả về bytes PDF."""
    pdf = _Report(format="A4")
    _font(pdf)
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_margins(15, 14, 15)
    pdf.add_page()
    title = lambda n: RESULT_NAMES.get(n, n)
    total = sum(len(d) for _, d in results)
    zone_a = sum(d["zone"] == "A" for _, ds in results for d in ds)

    # Tiêu đề + kết luận nhanh
    pdf.set_font("main", "B", 17)
    pdf.cell(0, 9, "BÁO CÁO KIỂM TRA PIXEL LỖI CAMERA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("main", size=10)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f"Loại kiểm tra: {MODE_NAMES.get(mode, mode)}   ·   Thời gian lập: "
                   f"{datetime.now():%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    ok = total == 0
    pdf.set_fill_color(*((225, 245, 233) if ok else (255, 236, 234)))
    pdf.set_text_color(*((31, 130, 70) if ok else (190, 45, 35)))
    pdf.set_font("main", "B", 13)
    pdf.cell(0, 12, "  Không phát hiện điểm lỗi" if ok else f"  Phát hiện {total} điểm lỗi ({zone_a} ở vùng giữa A)",
             fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*INK)
    pdf.set_fill_color(255, 255, 255)   # màu nền khung kết luận không được lan sang các bảng

    _heading(pdf, "1. Điều kiện chụp")
    rows = [(label, f"{info[k]}" + (f" ({info.get('iso_source')})" if k == "iso" and info.get("iso_source") else ""))
            for k, label in INFO_ROWS if k in info]
    _table(pdf, ("Thông tin", "Giá trị"), rows, (45, 135))

    _heading(pdf, "2. Kết quả tổng hợp")
    _table(pdf, ("Kết quả", "Tổng", "Vùng A", "Đơn", "Cụm", "Đường"),
           [(title(n), len(ds), *(sum(d[k] == v for d in ds) for k, v in
             (("zone", "A"), ("kind", "single"), ("kind", "cluster"), ("kind", "line")))) for n, ds in results],
           (60, 24, 24, 24, 24, 24))
    for note in notes:
        warn = note.startswith(("WARNING", "NOTE"))
        pdf.set_text_color(*((180, 110, 0) if warn else MUTED))
        pdf.multi_cell(0, 5, ("! " if warn else "· ") + note, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*INK)

    _heading(pdf, "3. Thông số phân tích")
    specs = [s for s in params.SPEC if mode in s["modes"]]
    _table(pdf, ("Thông số", "Giá trị", "Mặc định"),
           [(s["label"], f"{used_params.get(s['key'], s['default'])}" +
             (" *" if used_params.get(s["key"], s["default"]) != s["default"] else ""), s["default"]) for s in specs],
           (120, 30, 30))
    pdf.set_font("main", size=8.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, "* khác mặc định", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*INK)

    # Ảnh co lại cho vừa chỗ còn trống; còn < 90 mm thì sang trang mới (cả tiêu đề, để tiêu đề không nằm lẻ)
    room = lambda: pdf.h - pdf.b_margin - pdf.get_y() - 12
    ratio = image.shape[0] / image.shape[1]
    if ratio * pdf.epw > room() - 14 and room() - 14 < 90:
        pdf.add_page()
    _heading(pdf, "4. Vị trí điểm lỗi")
    jpg = mark_image(image, size, results, zone)
    w = min(pdf.epw, room() / ratio)
    pdf.image(BytesIO(jpg), x=pdf.l_margin + (pdf.epw - w) / 2, w=w)
    pdf.set_font("main", size=8.5)
    pdf.set_text_color(*MUTED)
    legend = " · ".join(f"{title(n)} = {['đỏ', 'cam', 'vàng', 'xanh lá'][i % 4]}" for i, (n, _) in enumerate(results))
    pdf.multi_cell(0, 4.5, f"Ảnh đầu tiên của bộ thứ nhất ({size[0]}×{size[1]}). Vòng tròn: {legend}. "
                           "Khung xám: vùng giữa A.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*INK)

    _heading(pdf, "5. Danh sách điểm lỗi")
    flat = [(title(n), d) for n, ds in results for d in ds]
    if not flat:
        pdf.cell(0, 6, "Không có điểm lỗi nào.", new_x="LMARGIN", new_y="NEXT")
    else:
        _table(pdf, ("#", "Kết quả", "x", "y", "Vùng", "Loại", "Số px"),
               [(i + 1, n, d["x"], d["y"], d["zone"], KIND_VI.get(d["kind"], d["kind"]), d["size"])
                for i, (n, d) in enumerate(flat[:MAX_ROWS])], (12, 50, 24, 24, 18, 28, 24))
        if len(flat) > MAX_ROWS:
            pdf.set_text_color(*MUTED)
            pdf.cell(0, 6, f"Chỉ hiện {MAX_ROWS}/{len(flat)} điểm đầu; danh sách đầy đủ ở file .json / .csv.",
                     new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
