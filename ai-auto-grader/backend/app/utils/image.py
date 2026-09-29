"""图像预处理工具：纠斜、去噪、去底色、二值化、透视矫正、区域切割。

所有坐标（区域 x/y/width/height）均采用 0~1000 的相对坐标系，
与模板设计器保持一致，渲染/切割时按图像实际像素尺寸换算。
"""

from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

RELATIVE_MAX = 1000.0


def load_image(path: str | Path) -> np.ndarray:
    """读取图像，统一为 BGR 三通道。支持中文路径。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取图像: {path}")
    return image


def save_image(image: np.ndarray, path: str | Path) -> None:
    """保存图像，支持中文路径。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix or ".png"
    ok, buf = cv2.imencode(ext, image)
    if not ok:
        raise ValueError(f"无法编码图像: {path}")
    buf.tofile(str(path))


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def encode_png(image: np.ndarray) -> bytes:
    """将图像编码为 PNG 字节流，用于直接返回给前端预览。"""
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("无法编码 PNG 图像")
    return buf.tobytes()


def detect_tilt_angle(image: np.ndarray, max_angle: float = 15.0, step: float = 0.5) -> float:
    """基于投影轮廓法估计文档倾斜角度（度）。返回 0 表示未检测到明显倾斜。

    对候选角度逐一旋转二值化图像，取行投影差分平方和最大的角度作为纠斜角；
    若相对 0° 无明显改善（<3%），则判定文档基本水平，返回 0。
    """
    gray = to_gray(image)
    h, w = gray.shape[:2]
    scale = min(1.0, 800.0 / max(w, 1))
    if scale < 1.0:
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    h, w = binary.shape[:2]
    center = (w / 2, h / 2)

    def score_at(angle: float) -> float:
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(binary, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        projection = np.sum(rotated, axis=1, dtype=np.float64)
        return float(np.sum(np.diff(projection) ** 2))

    base_score = score_at(0.0)
    best_angle, best_score = 0.0, base_score
    for angle in np.arange(-max_angle, max_angle + 1e-6, step):
        if abs(angle) < 1e-6:
            continue
        score = score_at(angle)
        if score > best_score:
            best_score, best_angle = score, float(angle)

    if base_score <= 0 or best_score < base_score * 1.03:
        return 0.0
    if abs(best_angle) > max_angle:
        return 0.0
    return best_angle


def deskew_image(image: np.ndarray, max_angle: float = 15.0) -> Tuple[np.ndarray, float]:
    """图像纠斜，返回 (纠斜后图像, 实际旋转角度)。"""
    angle = detect_tilt_angle(image, max_angle=max_angle)
    if abs(angle) < 0.1:
        return image, 0.0
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, float(angle)


def remove_background(image: np.ndarray) -> np.ndarray:
    """去底色：按大核闭运算估计背景并做归一化，缓解纸张阴影/底色不均。"""
    gray = to_gray(image)
    background = cv2.morphologyEx(
        gray, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)),
    )
    normalized = cv2.divide(gray, background, scale=255)
    return normalized


def denoise_image(image: np.ndarray) -> np.ndarray:
    """去噪：对灰度图使用中值滤波，抑制椒盐噪声。"""
    gray = to_gray(image)
    return cv2.medianBlur(gray, 3)


def binarize_image(image: np.ndarray) -> np.ndarray:
    """自适应二值化，适应光照不均的扫描件。"""
    gray = to_gray(image)
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=10,
    )


def order_points(points: np.ndarray) -> np.ndarray:
    """将四个点排序为：左上、右上、右下、左下。"""
    points = np.asarray(points, dtype="float32")
    rect = np.zeros((4, 2), dtype="float32")
    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]
    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def correct_perspective(image: np.ndarray, points: List[List[float]]) -> np.ndarray:
    """四点透视矫正。points 为图像像素坐标下的 4 个点。"""
    pts = order_points(np.array(points, dtype="float32"))
    (tl, tr, br, bl) = pts
    width = max(int(np.linalg.norm(br - bl)), int(np.linalg.norm(tr - tl)))
    height = max(int(np.linalg.norm(tr - br)), int(np.linalg.norm(tl - bl)))
    width, height = max(width, 1), max(height, 1)
    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(pts, dst)
    return cv2.warpPerspective(image, matrix, (width, height))


def preprocess_page(
    image: np.ndarray,
    *,
    deskew: bool = True,
    max_tilt: float = 15.0,
    perspective_points: Optional[List[List[float]]] = None,
    to_binary: bool = False,
) -> Tuple[np.ndarray, dict]:
    """答卷页预处理流水线。

    返回 (处理后的图像, 元信息)，元信息包含倾斜角度、是否透视矫正、倾斜是否超限。
    """
    meta = {"tilt_angle": 0.0, "tilt_exceed": False, "perspective_corrected": False}

    working = image
    if perspective_points and len(perspective_points) == 4:
        working = correct_perspective(working, perspective_points)
        meta["perspective_corrected"] = True

    if deskew:
        working, angle = deskew_image(working, max_angle=max_tilt)
        meta["tilt_angle"] = angle
        meta["tilt_exceed"] = abs(angle) >= max_tilt - 0.01

    working = denoise_image(working)
    working = remove_background(working)
    if to_binary:
        working = binarize_image(working)

    # 统一输出 BGR，便于后续存取与展示
    if working.ndim == 2:
        working = cv2.cvtColor(working, cv2.COLOR_GRAY2BGR)
    return working, meta


def relative_to_pixels(
    x: float, y: float, width: float, height: float,
    image_width: int, image_height: int,
) -> Tuple[int, int, int, int]:
    """0~1000 相对坐标 → 像素坐标 (x0, y0, x1, y1)，并裁剪到图像范围内。"""
    x0 = int(round(x / RELATIVE_MAX * image_width))
    y0 = int(round(y / RELATIVE_MAX * image_height))
    x1 = int(round((x + width) / RELATIVE_MAX * image_width))
    y1 = int(round((y + height) / RELATIVE_MAX * image_height))
    x0 = max(0, min(x0, image_width - 1))
    y0 = max(0, min(y0, image_height - 1))
    x1 = max(x0 + 1, min(x1, image_width))
    y1 = max(y0 + 1, min(y1, image_height))
    return x0, y0, x1, y1


def crop_region(
    image: np.ndarray,
    x: float, y: float, width: float, height: float,
) -> np.ndarray:
    """按相对坐标从整页图像中切割区域。"""
    h, w = image.shape[:2]
    x0, y0, x1, y1 = relative_to_pixels(x, y, width, height, w, h)
    return image[y0:y1, x0:x1].copy()