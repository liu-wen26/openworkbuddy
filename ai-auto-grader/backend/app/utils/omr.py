"""OMR 填涂识别：考号区（后续可复用于选择题）填涂判定。

主方法：网格采样。答题卡由本系统渲染，考号区“列（考号位）× 行（0~9）”
的填涂块位置可由模板区域几何精确还原，直接在图像上对每个块的核心区域采样，
即可稳定区分填涂/未填涂，避免轮廓检测在扫描噪声下的不稳定性。

回退方法：轮廓检测聚类（用于外部自制答题卡或几何参数缺失时）。
"""

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from app.utils.image import to_gray

Bubble = Tuple[float, float, float]  # (cx, cy, fill_ratio)


# ---------------- 网格采样（主方法） ----------------

def _binarize(gray: np.ndarray) -> np.ndarray:
    """Otsu 全局二值化（反相）：墨迹为 255，背景为 0。"""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return binary


def _sample_core_ratio(
    binary: np.ndarray, cx: float, cy: float, radius: int
) -> float:
    h, w = binary.shape[:2]
    x0 = max(0, int(round(cx - radius)))
    x1 = min(w, int(round(cx + radius)) + 1)
    y0 = max(0, int(round(cy - radius)))
    y1 = min(h, int(round(cy + radius)) + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    patch = binary[y0:y1, x0:x1]
    return float(np.count_nonzero(patch)) / max(patch.size, 1)


def read_by_grid(
    region_image: np.ndarray,
    digits: int,
    column_x_fractions: Sequence[float],
    row_y_fractions: Sequence[float],
    fill_threshold: float = 0.45,
    bubble_radius_fraction: float = 0.01,
) -> Optional[Tuple[str, float]]:
    """按已知网格几何采样识别考号。

    column_x_fractions：每个考号位（数字列）在区域内的 x 相对位置（0~1）。
    row_y_fractions：0~9 每一行在区域内的 y 相对位置（0~1）。
    bubble_radius_fraction：采样半径相对区域高度的比例（仅取填涂块核心）。
    """
    gray = to_gray(region_image)
    if gray.size == 0 or len(column_x_fractions) < digits or len(row_y_fractions) < 10:
        return None
    if max(row_y_fractions) > 1.02 or min(row_y_fractions) < -0.02:
        return None
    if max(column_x_fractions) > 1.02 or min(column_x_fractions) < -0.02:
        return None

    binary = _binarize(gray)
    h, w = gray.shape[:2]
    radius = max(2, int(round(bubble_radius_fraction * h)))

    value_chars: List[str] = []
    confidences: List[float] = []

    for c in range(digits):
        cx = column_x_fractions[c] * w
        ratios = [
            _sample_core_ratio(binary, cx, row_y_fractions[d] * h, radius)
            for d in range(10)
        ]
        best_i = int(np.argmax(ratios))
        best = ratios[best_i]
        if best < fill_threshold:
            return None
        second = max(v for i, v in enumerate(ratios) if i != best_i)
        value_chars.append(str(best_i))
        margin = best - second
        confidences.append(float(np.clip(0.6 * min(best / 0.8, 1.0) + 0.4 * min(margin / 0.4, 1.0), 0.0, 1.0)))

    return "".join(value_chars), float(np.mean(confidences))


# ---------------- 轮廓检测（回退方法） ----------------

def _mark_mask(gray: np.ndarray) -> np.ndarray:
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=25,
        C=8,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)


def detect_bubbles(gray: np.ndarray) -> List[Bubble]:
    """检测圆形填涂块，返回其中心与内部填涂占比。

    使用 RETR_LIST：答题卡区域外框是闭合矩形，会屏蔽内部轮廓。
    轮廓按中心去重，保留填涂占比更高者。
    """
    mask = _mark_mask(gray)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    min_area = max(8.0, (h * w) * 0.00002)
    max_area = (h * w) * 0.05
    raw: List[Bubble] = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter <= 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity < 0.5:
            continue
        m = cv2.moments(cnt)
        if m["m00"] == 0:
            continue
        cx = m["m10"] / m["m00"]
        cy = m["m01"] / m["m00"]

        filled = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(filled, [cnt], -1, 255, thickness=cv2.FILLED)
        fill_ratio = float(np.count_nonzero(cv2.bitwise_and(mask, mask, mask=filled))) / max(area, 1.0)
        raw.append((cx, cy, min(fill_ratio, 1.0)))

    merged: List[Bubble] = []
    tolerance = max(3.0, min(h, w) * 0.02)
    for cx, cy, fill in sorted(raw, key=lambda b: -b[2]):
        if any(abs(mx - cx) <= tolerance and abs(my - cy) <= tolerance for mx, my, _ in merged):
            continue
        merged.append((cx, cy, fill))
    return merged


def _cluster_1d(values: Sequence[float], k: int, iterations: int = 30) -> List[float]:
    vals = np.asarray(values, dtype=float)
    centers = np.linspace(vals.min(), vals.max(), k)
    for _ in range(iterations):
        idx = np.abs(vals[:, None] - centers[None, :]).argmin(axis=1)
        new_centers = np.array([
            vals[idx == j].mean() if np.any(idx == j) else centers[j]
            for j in range(k)
        ])
        if np.allclose(new_centers, centers):
            break
        centers = new_centers
    return sorted(float(c) for c in centers)


def read_by_contours(
    region_image: np.ndarray, digits: int, fill_threshold: float
) -> Optional[Tuple[str, float]]:
    gray = to_gray(region_image)
    bubbles = detect_bubbles(gray)
    if len(bubbles) < digits * 6:
        return None

    col_centers = _cluster_1d([b[0] for b in bubbles], digits)
    row_centers = _cluster_1d([b[1] for b in bubbles], 10)
    if len(col_centers) != digits or len(row_centers) != 10:
        return None

    col_spacing = (col_centers[-1] - col_centers[0]) / max(digits - 1, 1)
    row_spacing = (row_centers[-1] - row_centers[0]) / 9.0

    value_chars: List[str] = []
    confidences: List[float] = []
    for col in col_centers:
        candidates = [
            b for b in bubbles
            if abs(b[0] - col) <= max(col_spacing * 0.4, 3)
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda b: b[2])
        if best[2] < fill_threshold:
            return None
        row_index = int(np.argmin([abs(best[1] - rc) for rc in row_centers]))
        if abs(best[1] - row_centers[row_index]) > max(row_spacing * 0.5, 3):
            return None
        second = max((b[2] for b in candidates if b is not best), default=0.0)
        value_chars.append(str(row_index))
        confidences.append(float(np.clip(0.5 * best[2] + 0.5 * min((best[2] - second) / 0.3, 1.0), 0.0, 1.0)))

    return "".join(value_chars), float(np.mean(confidences))


# ---------------- 对外入口 ----------------

def recognize_exam_number(
    region_image: np.ndarray,
    digits: int = 9,
    fill_threshold: float = 0.45,
    column_x_fractions: Optional[Sequence[float]] = None,
    row_y_fractions: Optional[Sequence[float]] = None,
    bubble_radius_fraction: float = 0.01,
) -> Tuple[Optional[str], float]:
    """识别考号区域的填涂结果，返回 (考号字符串 或 None, 置信度 0~1)。"""
    gray = to_gray(region_image)
    if gray.size == 0:
        return None, 0.0

    if column_x_fractions and row_y_fractions:
        result = read_by_grid(
            gray, digits, column_x_fractions, row_y_fractions,
            fill_threshold=fill_threshold,
            bubble_radius_fraction=bubble_radius_fraction,
        )
        if result is not None and len(result[0]) == digits:
            return result

    result = read_by_contours(gray, digits, fill_threshold)
    if result is not None and len(result[0]) == digits:
        return result

    return None, 0.0