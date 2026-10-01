"""选择题网格生成与气泡坐标解析。

标注式答题卡不再依赖渲染常量反推气泡位置：用户框住整个选择题区后，
由本模块按"题数 × 选项数 × 栏数"自动切成一题一个区域，并把每个选项气泡
的中心坐标写入 region.option_spec 持久化，因此可适配任意真实印刷答题卡
（横排 / 竖排 / 多栏 / 任意间距）。
"""

import math
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from app.models.template_config import TemplateRegion

MAX_QUESTIONS = 200
MAX_COLUMNS = 8
MAX_OPTIONS = 10

# 气泡中心在"区域内的分布带"（0~1）：默认给左侧题号列留出空间
DEFAULT_X_BAND = (0.18, 0.92)
DEFAULT_Y_BAND = (0.10, 0.90)
RADIUS_RATIO = 0.35  # 采样半径 ≈ 相邻气泡中心间距的 35%

# 考号填涂格（dots × 10 行）默认分布带
DEFAULT_DIGIT_X_BAND = (0.10, 0.92)
DEFAULT_DIGIT_Y_BAND = (0.08, 0.94)
MAX_DIGITS = 16


def build_choice_grid(
    box: Dict[str, float],
    *,
    page_index: int = 0,
    start_question: int = 1,
    question_count: int = 10,
    options_count: int = 4,
    columns: int = 1,
    direction: str = "horizontal",
    score: float = 0.0,
    page_width_px: int = 0,
    page_height_px: int = 0,
    x_band: Optional[Tuple[float, float]] = None,
    y_band: Optional[Tuple[float, float]] = None,
) -> List[dict]:
    """把框选出的选择题大区切成"一题一区域"，返回可直接入库的区域载荷列表。"""
    _validate(box, question_count, options_count, columns, direction)

    rows = math.ceil(question_count / columns)
    col_w = float(box["width"]) / columns
    row_h = float(box["height"]) / rows

    x_band = x_band or (DEFAULT_X_BAND if direction == "horizontal" else (0.5, 0.5))
    y_band = y_band or (DEFAULT_Y_BAND if direction == "vertical" else (0.5, 0.5))

    payloads: List[dict] = []
    for idx in range(question_count):
        col = idx // rows
        row = idx % rows
        region_x = float(box["x"]) + col * col_w
        region_y = float(box["y"]) + row * row_h
        spec = _option_spec(
            direction, options_count, x_band, y_band,
            region_w=col_w, region_h=row_h,
            page_w=page_width_px, page_h=page_height_px,
        )
        payloads.append({
            "page_index": page_index,
            "region_type": "choice",
            "question_number": str(start_question + idx),
            "sub_question_number": None,
            "max_score": float(score),
            "x": round(region_x, 2),
            "y": round(region_y, 2),
            "width": round(col_w, 2),
            "height": round(row_h, 2),
            "options_count": options_count,
            "allow_multiple": False,
            "partial_score_rules": None,
            "knowledge_tags": None,
            "config": None,
            "group_key": None,
            "option_spec": spec,
        })
    return payloads


def _validate(box, question_count, options_count, columns, direction) -> None:
    for key in ("x", "y", "width", "height"):
        if key not in box:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"框选区域缺少字段 {key}")
    if float(box["width"]) <= 0 or float(box["height"]) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="框选区域宽高必须大于 0")
    if not 1 <= question_count <= MAX_QUESTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"题目数量需在 1~{MAX_QUESTIONS} 之间")
    if not 2 <= options_count <= MAX_OPTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"选项数需在 2~{MAX_OPTIONS} 之间")
    if not 1 <= columns <= MAX_COLUMNS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"栏数需在 1~{MAX_COLUMNS} 之间")
    if direction not in ("horizontal", "vertical"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="选项排列仅支持 horizontal / vertical")


def _option_spec(
    direction: str,
    options_count: int,
    x_band: Tuple[float, float],
    y_band: Tuple[float, float],
    *,
    region_w: float,
    region_h: float,
    page_w: int,
    page_h: int,
) -> dict:
    """生成某道选择题的气泡坐标（区域相对 0~1000）与采样半径（区域高度占比）。"""
    labels = [chr(ord("A") + i) for i in range(options_count)]
    bubbles: List[dict] = []

    if direction == "horizontal":
        start, end = x_band
        step = (end - start) / options_count
        for i, label in enumerate(labels):
            cx = (start + (i + 0.5) * step) * 1000
            bubbles.append({"label": label, "cx": round(cx, 2), "cy": 500.0})
        radius = _radius(
            spacing_px=(end - start) * region_w / 1000.0 * max(page_w, 1) / options_count,
            region_h_px=region_h / 1000.0 * max(page_h, 1),
            fallback=0.08,
        )
    else:
        start, end = y_band
        step = (end - start) / options_count
        for i, label in enumerate(labels):
            cy = (start + (i + 0.5) * step) * 1000
            bubbles.append({"label": label, "cx": 500.0, "cy": round(cy, 2)})
        radius = RADIUS_RATIO / options_count

    return {
        "kind": "choice",
        "direction": direction,
        "option_labels": labels,
        "radius": round(radius, 4),
        "bubbles": bubbles,
    }


def _radius(spacing_px: float, region_h_px: float, fallback: float) -> float:
    if region_h_px <= 0 or spacing_px <= 0:
        return fallback
    return float(min(max(RADIUS_RATIO * spacing_px / region_h_px, 0.02), 0.35))


# ---------------- 解析（供判分服务使用） ----------------

def bubble_centers(region: TemplateRegion) -> Optional[Tuple[List[Tuple[float, float]], float]]:
    """从区域配置解析气泡中心（0~1 相对区域）与采样半径（区域高度占比）。

    旧模板没有 option_spec，返回 None，由调用方回退到渲染常量路径。
    """
    spec = region.option_spec
    if not isinstance(spec, dict):
        return None
    if spec.get("kind") not in (None, "choice"):
        return None
    raw = spec.get("bubbles")
    if not isinstance(raw, list) or len(raw) < 2:
        return None

    centers: List[Tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        try:
            cx = float(item["cx"]) / 1000.0
            cy = float(item["cy"]) / 1000.0
        except (KeyError, TypeError, ValueError):
            return None
        centers.append((cx, cy))

    try:
        radius = float(spec.get("radius", 0.05))
    except (TypeError, ValueError):
        radius = 0.05
    return centers, min(max(radius, 0.005), 0.5)


# ---------------- 考号填涂格（digits × 10 行） ----------------

def build_digit_grid(
    box: Dict[str, float],
    *,
    digits: int = 9,
    x_band: Optional[Tuple[float, float]] = None,
    y_band: Optional[Tuple[float, float]] = None,
) -> dict:
    """为考号区生成填涂格坐标：digits 列 × 10 行（数字 0~9）。

    返回可直接写入 region.option_spec 的字典。列 / 行中心均为区域相对坐标 0~1000。
    """
    _validate_digit_box(box, digits)
    x_band = x_band or DEFAULT_DIGIT_X_BAND
    y_band = y_band or DEFAULT_DIGIT_Y_BAND

    step_x = (x_band[1] - x_band[0]) / digits
    columns = [round((x_band[0] + (i + 0.5) * step_x) * 1000, 2) for i in range(digits)]

    step_y = (y_band[1] - y_band[0]) / 10
    rows = [round((y_band[0] + (d + 0.5) * step_y) * 1000, 2) for d in range(10)]

    return {
        "kind": "digit",
        "digits": digits,
        "row_labels": [str(d) for d in range(10)],
        "columns": columns,
        "rows": rows,
        "radius": round(min(0.045, step_y * 0.45), 4),
    }


def _validate_digit_box(box: Dict[str, float], digits: int) -> None:
    for key in ("x", "y", "width", "height"):
        if key not in box:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"框选区域缺少字段 {key}")
    if float(box["width"]) <= 0 or float(box["height"]) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="框选区域宽高必须大于 0")
    if not 1 <= digits <= MAX_DIGITS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"考号位数需在 1~{MAX_DIGITS} 之间")


def digit_grid(region: TemplateRegion) -> Optional[Tuple[List[float], List[float], float]]:
    """解析考号区填涂格：返回 (列 x 比例, 行 y 比例, 采样半径比例)。

    无填涂格配置返回 None，由调用方回退到几何常量 / 轮廓检测路径。
    """
    spec = region.option_spec
    if not isinstance(spec, dict) or spec.get("kind") != "digit":
        return None
    columns = spec.get("columns")
    rows = spec.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return None
    if len(columns) < 1 or len(rows) < 10:
        return None
    try:
        cols = [float(c) / 1000.0 for c in columns]
        ys = [float(r) / 1000.0 for r in rows]
        radius = float(spec.get("radius", 0.02))
    except (TypeError, ValueError):
        return None
    return cols, ys, min(max(radius, 0.005), 0.5)