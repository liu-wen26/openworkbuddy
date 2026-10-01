"""AI 评分与识别服务抽象层（F7-03）。

统一三种实现：
  - OpenAICompatibleProvider：云端 OpenAI 兼容 /chat/completions（视觉）
  - LocalModelProvider：本地私有化模型（同样走 OpenAI 兼容协议，可自定义地址与模型）
  - MockAIProvider：未配置任何大模型凭证时的启发式兜底，保证流程可跑通（结果带 mock 标记）

两类能力：
  - score_subjective：主观题评分，返回 AIScoreResult
  - ocr_fields：区域信息识别（手写考号 / 姓名 / 班级），返回 {字段名: 文本}

由上层落库并做低置信度 / 未识别转异常处理。
"""

import base64
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import numpy as np

from app.core.config import get_settings
from app.utils import image as image_utils

logger = logging.getLogger(__name__)
settings = get_settings()

DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_LOCAL_BASE = "http://localhost:8000/v1"

SYSTEM_PROMPT = (
    "你是一名资深阅卷教师。请根据给定的题目标准答案与采分点，对学生的作答图片进行评分，"
    "并严格以 JSON 返回：{\"score\": 数值, \"comment\": \"评语\", \"confidence\": 0~1 的置信度}。"
    "score 不得超过满分；当图片无法辨认或无法确定时，降低 confidence。"
)

# 待识别字段的中文名，用于组装 OCR 指令
OCR_FIELD_LABELS = {
    "exam_number": "考号",
    "name": "姓名",
    "class_name": "班级",
}

OCR_SYSTEM_PROMPT = (
    "你是一名答题卡信息识别引擎。请只识别图片中指定字段的手写或打印内容，"
    "并严格以 JSON 返回，键为字段英文名、值为识别出的文本；无法识别的字段返回空字符串。"
    "只做识别，不要计算、不要解释、不要输出 JSON 以外的任何文字。"
)

# 识别失败（未配置视觉模型 / 调用异常）时返回空结果，由上层转异常，不阻断主流程
OCR_EMPTY_RESULT: Dict[str, str] = {}


@dataclass
class AIScoreResult:
    score: float
    comment: str
    confidence: float
    model: str
    provider: str
    detail: Dict[str, Any] = field(default_factory=dict)


class AIServiceProvider(ABC):
    """AI 评分与识别提供方统一接口。"""

    name = "base"

    @abstractmethod
    def score_subjective(self, image_bytes: bytes, context: Dict[str, Any]) -> AIScoreResult:
        raise NotImplementedError

    def ocr_fields(
        self, image_bytes: bytes, fields: List[str], hint: Optional[str] = None
    ) -> Dict[str, str]:
        """识别图片中指定字段（考号 / 姓名 / 班级）。

        默认实现返回空结果：不具备视觉能力的提供方（如启发式兜底）不应阻断主流程，
        由上层把"未识别"转成人工处理的异常。
        """
        return dict(OCR_EMPTY_RESULT)


# ---------------- 提示词构建 ----------------

def _build_user_prompt(context: Dict[str, Any]) -> str:
    max_score = context.get("max_score") or 0
    lines = [
        f"题目：第 {context.get('question_number') or '-'} 题",
        f"满分：{max_score}",
    ]
    if context.get("standard_answer"):
        lines.append(f"标准答案：{context['standard_answer']}")
    points = context.get("scoring_points")
    if points:
        lines.append(f"采分点：{json.dumps(points, ensure_ascii=False)}")
    if context.get("deduction_notes"):
        lines.append(f"扣分说明：{context['deduction_notes']}")
    lines.append("请评分并返回 JSON。")
    template = context.get("prompt_template")
    if template:
        lines.insert(0, template)
    return "\n".join(lines)


def _parse_model_json(text: str, max_score: float) -> Optional[Dict[str, Any]]:
    """从模型输出中提取 JSON，容忍 ```json 代码块与多余文字。"""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if "score" not in data:
        return None
    try:
        data["score"] = float(data["score"])
    except (TypeError, ValueError):
        return None
    if max_score:
        data["score"] = max(0.0, min(data["score"], float(max_score)))
    try:
        data["confidence"] = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        data["confidence"] = 0.0
    data["confidence"] = max(0.0, min(data["confidence"], 1.0))
    return data


def _build_ocr_prompt(fields: List[str], hint: Optional[str]) -> str:
    lines = ["请识别图片中的以下字段："]
    for f in fields:
        lines.append(f"- {f}（{OCR_FIELD_LABELS.get(f, f)}）")
    if hint:
        lines.append(f"参考信息：{hint}")
    example = "{" + ", ".join(f'"{f}": "..."' for f in fields) + "}"
    lines.append(f"严格返回 JSON，例如：{example}")
    return "\n".join(lines)


def _parse_ocr_json(text: str, fields: List[str]) -> Dict[str, str]:
    """从模型输出中提取字段 JSON，容忍代码块与多余说明；仅保留请求的字段。"""
    if not text or not fields:
        return {}
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    result: Dict[str, str] = {}
    for f in fields:
        value = data.get(f)
        result[f] = "" if value is None else str(value).strip()
    return result


# ---------------- OpenAI 兼容实现 ----------------

class OpenAICompatibleProvider(AIServiceProvider):
    name = "openai"

    def __init__(self, base_url: str, api_key: Optional[str], model: str, timeout: float = 60.0):
        self.base_url = (base_url or DEFAULT_OPENAI_BASE).rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def score_subjective(self, image_bytes: bytes, context: Dict[str, Any]) -> AIScoreResult:
        max_score = float(context.get("max_score") or 0)
        b64 = base64.b64encode(image_bytes).decode()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _build_user_prompt(context)},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                },
            ],
            "temperature": 0,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        content = body["choices"][0]["message"]["content"]
        parsed = _parse_model_json(content, max_score)
        if parsed is None:
            return AIScoreResult(
                score=0.0, comment="模型返回无法解析", confidence=0.0,
                model=self.model, provider=self.name, detail={"raw": content},
            )
        return AIScoreResult(
            score=parsed["score"],
            comment=parsed.get("comment", ""),
            confidence=parsed["confidence"],
            model=self.model,
            provider=self.name,
            detail={"raw": content},
        )

    def ocr_fields(
        self, image_bytes: bytes, fields: List[str], hint: Optional[str] = None
    ) -> Dict[str, str]:
        """调用视觉模型识别区域内的手写/打印字段。"""
        if not fields or not image_bytes:
            return {}
        b64 = base64.b64encode(image_bytes).decode()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": OCR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _build_ocr_prompt(fields, hint)},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                },
            ],
            "temperature": 0,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()
            content = body["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            # 识别失败不阻断导入：上层会按"未识别"生成人工处理异常
            logger.warning("OCR 调用失败 model=%s: %s", self.model, exc)
            return dict(OCR_EMPTY_RESULT)
        return _parse_ocr_json(content, fields)


class LocalModelProvider(OpenAICompatibleProvider):
    """本地私有化模型：默认使用本地 OpenAI 兼容服务，无需 API Key。"""

    name = "local"

    def __init__(self, base_url: Optional[str], model: str, timeout: float = 60.0):
        super().__init__(base_url or DEFAULT_LOCAL_BASE, None, model, timeout)


# ---------------- 兜底实现 ----------------

class MockAIProvider(AIServiceProvider):
    """未配置大模型时的启发式兜底：按作答墨迹量估算得分占比。

    仅用于本地联调，结果带 provider=mock，便于与真实模型区分。
    """

    name = "mock"

    def ocr_fields(
        self, image_bytes: bytes, fields: List[str], hint: Optional[str] = None
    ) -> Dict[str, str]:
        """启发式兜底不具备视觉识别能力，返回空结果，由上层转人工处理异常。"""
        logger.warning("当前为启发式兜底，无法识别字段 %s，需人工指定", fields)
        return dict(OCR_EMPTY_RESULT)

    def score_subjective(self, image_bytes: bytes, context: Dict[str, Any]) -> AIScoreResult:
        max_score = float(context.get("max_score") or 0)
        ratio = self._ink_ratio(image_bytes)
        # 墨迹占比映射为得分率：空白≈0，写满≈1；并保留一定保守性
        score = round(max_score * min(ratio / 0.18, 1.0), 2)
        confidence = round(min(ratio / 0.18, 1.0) * 0.6, 3)
        return AIScoreResult(
            score=score,
            comment=f"[启发式兜底评分] 依据作答墨迹占比 {ratio:.3f} 估算，未接入大模型。",
            confidence=confidence,
            model="heuristic",
            provider=self.name,
            detail={"ink_ratio": round(ratio, 4)},
        )

    @staticmethod
    def _ink_ratio(image_bytes: bytes) -> float:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = image_utils.decode_image(arr)
        if img is None:
            return 0.0
        gray = image_utils.to_gray(img)
        if gray.size == 0:
            return 0.0
        dark = float(np.count_nonzero(gray < 128))
        return dark / max(gray.size, 1)


# ---------------- 工厂 ----------------

def get_ai_provider() -> AIServiceProvider:
    """构建 AI 提供方：优先读取系统设置中的大模型配置，回落到环境变量。"""
    from app.services import settings_service

    config = settings_service.get_llm_config()
    if not config.get("enabled", True):
        logger.info("大模型配置已停用，AI 评分使用启发式兜底")
        return MockAIProvider()

    provider = (config.get("provider") or settings.LLM_PROVIDER or "openai").lower()
    model = config.get("model") or settings.LLM_DEFAULT_MODEL
    base = config.get("api_base") or settings.LLM_API_BASE
    api_key = config.get("api_key") or settings.LLM_API_KEY

    if provider == "mock":
        return MockAIProvider()
    if provider == "local":
        return LocalModelProvider(base, model)
    if api_key:
        return OpenAICompatibleProvider(base or DEFAULT_OPENAI_BASE, api_key, model)
    logger.warning("未配置 LLM_API_KEY，AI 评分回退到启发式兜底（mock）")
    return MockAIProvider()


def check_llm_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """校验大模型连通性：对 OpenAI 兼容服务探测 /models 列表。"""
    provider = (config.get("provider") or "openai").lower()
    model = config.get("model") or ""
    if provider == "mock":
        return {"ok": True, "provider": "mock", "message": "当前为启发式兜底，未接入真实大模型"}
    base = (config.get("api_base") or (DEFAULT_LOCAL_BASE if provider == "local" else DEFAULT_OPENAI_BASE)).rstrip("/")
    api_key = config.get("api_key")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{base}/models", headers=headers)
            resp.raise_for_status()
        return {"ok": True, "provider": provider, "model": model, "message": f"连接成功（{base}）"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "provider": provider, "model": model, "message": f"连接失败：{exc}"}