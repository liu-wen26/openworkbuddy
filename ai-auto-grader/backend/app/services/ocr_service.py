"""答题卡信息 OCR 服务。

按模板区域（考号区 / 姓名区 / 班级区）裁剪出作答图，调用视觉模型识别手写或打印内容，
并把结果归一化为可入库、可匹配花名册的取值。

职责边界：本模块只负责"取图 → 调模型 → 归一化"，不决定是否启用识别、也不做学生匹配；
启用开关与匹配策略由导入流水线（import_service）与预阅卷流水线（precheck_service）决定。
"""

import logging
import re
from typing import Dict, List, Optional, Sequence

import numpy as np

from app.services import ai_service
from app.utils import image as image_utils

logger = logging.getLogger(__name__)

# 模板区域类型 -> OCR 字段名
REGION_TO_FIELD = {
    "exam_number": "exam_number",
    "name": "name",
    "class": "class_name",
}

# 各字段在识别结果里可能带出的标签词，需要剥离后再入库
_LABEL_WORDS = {
    "exam_number": ("考号", "学号", "考籍号", "准考证号"),
    "name": ("姓名", "学生姓名", "学生"),
    "class_name": ("班级", "班别", "所在班级"),
}

_PUNCT = "：:，,。.、；;|｜-_/\\ \t\r\n\u3000"

_NAME_KEEP = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]")
_CLASS_KEEP = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff班年级组]")


def _strip_labels(value: str, field: str) -> str:
    """剥离形如 "姓名：李明" / "考号 02" 的标签前缀与分隔符。"""
    text = value.strip()
    for word in _LABEL_WORDS.get(field, ()):  # 长词优先，避免"学生姓名"被"学生"截断
        text = text.replace(word, "")
    return text.strip(_PUNCT)


def normalize_exam_number(value: Optional[str], digits: Optional[int] = None) -> str:
    """考号归一化：只保留数字；位数已知时截断多余位（不回填前导零，兼容花名册写法）。"""
    if not value:
        return ""
    text = _strip_labels(str(value), "exam_number")
    number = re.sub(r"\D", "", text)
    if digits and digits > 0 and len(number) > digits:
        number = number[:digits]
    return number


def normalize_name(value: Optional[str]) -> str:
    """姓名归一化：剥离标签，仅保留中英文字符与数字（去掉标点、空格）。"""
    if not value:
        return ""
    return _NAME_KEEP.sub("", _strip_labels(str(value), "name"))


def normalize_class_name(value: Optional[str]) -> str:
    """班级归一化：剥离标签，保留"七年级/1班"这类字符。"""
    if not value:
        return ""
    return _CLASS_KEEP.sub("", _strip_labels(str(value), "class_name"))


def _normalize(field: str, value: Optional[str], digits: Optional[int] = None) -> str:
    if field == "exam_number":
        return normalize_exam_number(value, digits)
    if field == "name":
        return normalize_name(value)
    if field == "class_name":
        return normalize_class_name(value)
    return (value or "").strip()


def recognize_fields(
    processed_page: np.ndarray,
    regions: Sequence,
    fields: Sequence[str],
    digits: Optional[int] = None,
    hint: Optional[str] = None,
) -> Dict[str, str]:
    """按区域识别指定字段。

    fields 取值：exam_number / name / class_name；每个字段取其对应区域逐一识别，
    识别为空或异常的字段不会出现在返回值中（由调用方转人工处理异常）。
    """
    requested = [f for f in fields if f]
    if not requested or processed_page is None or getattr(processed_page, "size", 0) == 0:
        return {}

    crops: Dict[str, bytes] = {}
    for region in regions:
        field = REGION_TO_FIELD.get(getattr(region, "region_type", ""))
        if field not in requested or field in crops:
            continue
        crop = image_utils.crop_region(
            processed_page,
            float(region.x), float(region.y), float(region.width), float(region.height),
        )
        if crop.size == 0 or min(crop.shape[:2]) < 4:
            continue
        crops[field] = image_utils.encode_png(crop)

    if not crops:
        return {}

    provider = ai_service.get_ai_provider()
    result: Dict[str, str] = {}
    for field, png in crops.items():
        try:
            raw = provider.ocr_fields(png, [field], hint=hint).get(field, "")
        except Exception as exc:  # noqa: BLE001  提供方已兜底，这里再兜一层保证不阻断导入
            logger.warning("字段 %s OCR 异常: %s", field, exc)
            continue
        value = _normalize(field, raw, digits)
        if value:
            result[field] = value
    return result