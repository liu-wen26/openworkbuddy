"""AI 评分服务抽象层（F7-03）。

统一三种实现：
  - OpenAICompatibleProvider：云端 OpenAI 兼容 /chat/completions（视觉）
  - LocalModelProvider：本地私有化模型（同样走 OpenAI 兼容协议，可自定义地址与模型）
  - MockAIProvider：未配置任何大模型凭证时的启发式兜底，保证流程可跑通（结果带 mock 标记）

所有实现返回统一的 AIScoreResult，由上层落库并做低置信度转异常处理。
"""

import base64
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

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


@dataclass
class AIScoreResult:
    score: float
    comment: str
    confidence: float
    model: str
    provider: str
    detail: Dict[str, Any] = field(default_factory=dict)


class AIServiceProvider(ABC):
    """AI 评分提供方统一接口。"""

    name = "base"

    @abstractmethod
    def score_subjective(self, image_bytes: bytes, context: Dict[str, Any]) -> AIScoreResult:
        raise NotImplementedError


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