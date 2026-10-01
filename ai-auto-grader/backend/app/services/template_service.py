import io
from typing import List
from uuid import UUID

import pymupdf as fitz  # PyMuPDF

# 纸张尺寸（单位：pt，72dpi）
PAPER_SIZES = {
    "A4": (595.0, 842.0),
    "A3": (842.0, 1191.0),
}

REGION_LABELS = {
    "exam_number": "考号",
    "name": "姓名",
    "class": "班级",
    "choice": "选择题",
    "subjective": "非选择题",
}

REGION_COLORS = {
    "exam_number": (0.09, 0.46, 0.94),
    "name": (0.06, 0.72, 0.51),
    "class": (0.45, 0.18, 0.82),
    "choice": (0.98, 0.63, 0.09),
    "subjective": (0.86, 0.24, 0.29),
}


def render_answer_card_pdf(template, regions: List, watermark: str = "") -> bytes:
    """根据模板与区域坐标生成空白答题卡 PDF。

    区域坐标以 0~1000 的相对坐标系存储，渲染时按页面实际尺寸换算。
    """
    width, height = PAPER_SIZES.get(template.paper_size, PAPER_SIZES["A4"])
    doc = fitz.open()

    for page_index in range(max(1, template.page_count)):
        page = doc.new_page(width=width, height=height)
        _draw_page_header(page, template, width, height, page_index)
        page_regions = [r for r in regions if r.page_index == page_index]
        for region in page_regions:
            _draw_region(page, region, width, height)
        if watermark:
            _draw_watermark(page, watermark, width, height)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _draw_page_header(page, template, width: float, height: float, page_index: int) -> None:
    title = template.title or "答题卡"
    page.insert_text(
        fitz.Point(width / 2 - len(title) * 7, 50),
        title,
        fontname="china-s",
        fontsize=18,
    )
    meta = f"考试：____________    班级：________    姓名：________    考号：____________"
    page.insert_text(fitz.Point(50, 80), meta, fontname="china-s", fontsize=10)
    page.draw_line(fitz.Point(40, 92), fitz.Point(width - 40, 92), color=(0.6, 0.6, 0.6), width=0.8)
    page.insert_text(
        fitz.Point(width - 90, height - 20),
        f"第 {page_index + 1} 页",
        fontname="china-s",
        fontsize=9,
    )


def _draw_region(page, region, page_width: float, page_height: float) -> None:
    x0 = float(region.x) / 1000.0 * page_width
    y0 = float(region.y) / 1000.0 * page_height
    w = float(region.width) / 1000.0 * page_width
    h = float(region.height) / 1000.0 * page_height
    rect = fitz.Rect(x0, y0, x0 + w, y0 + h)
    color = REGION_COLORS.get(region.region_type, (0.5, 0.5, 0.5))

    page.draw_rect(rect, color=color, width=1.0)

    label = REGION_LABELS.get(region.region_type, region.region_type)
    if region.question_number:
        label = f"{label} {region.question_number}"
    if region.sub_question_number:
        label = f"{label}-{region.sub_question_number}"

    page.insert_text(
        fitz.Point(rect.x0 + 4, rect.y0 + 12),
        label,
        fontname="china-s",
        fontsize=9,
        color=color,
    )

    if region.region_type == "choice":
        _draw_choice_bubbles(page, rect, region)
    elif region.region_type == "exam_number":
        _draw_exam_number_grid(page, rect, region)


def _draw_choice_bubbles(page, rect, region) -> None:
    options = region.options_count or 4
    letters = [chr(ord("A") + i) for i in range(options)]
    start_y = rect.y0 + 26
    gap = max(10.0, (rect.height - 30) / max(1, options))
    for i, letter in enumerate(letters):
        cy = start_y + i * gap
        if cy > rect.y1 - 4:
            break
        page.draw_circle(fitz.Point(rect.x0 + 16, cy), 5, color=(0.4, 0.4, 0.4), width=0.7)
        page.insert_text(fitz.Point(rect.x0 + 26, cy + 3), letter, fontname="china-s", fontsize=8)


def _draw_exam_number_grid(page, rect, region) -> None:
    digits = 9
    config = region.config or {}
    digits = int(config.get("digits", 9))
    start_x = rect.x0 + 12
    col_w = min(16.0, (rect.width - 20) / max(1, digits))
    for c in range(digits):
        cx = start_x + c * col_w
        for d in range(10):
            cy = rect.y0 + 26 + d * 12
            if cy > rect.y1 - 6:
                break
            page.draw_circle(fitz.Point(cx, cy), 4, color=(0.55, 0.55, 0.55), width=0.6)


def _draw_watermark(page, text: str, width: float, height: float) -> None:
    page.insert_text(
        fitz.Point(width * 0.2, height * 0.5),
        text,
        fontname="china-s",
        fontsize=48,
        color=(0.85, 0.85, 0.85),
        rotate=45,
    )