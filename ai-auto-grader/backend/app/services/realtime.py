"""实时推送基础设施（阶段 9）。

- 进程内 WebSocket 连接管理：按 topic 维护连接集合，向订阅者广播事件。
- 与同步业务代码的桥接：业务服务（导入、阅卷等）在同步上下文中调用 `publish`，
  内部通过主事件循环把广播调度回协程执行。
- 跨进程中继：当 USE_CELERY=True 时，任务在独立 Worker 进程中执行，进程内连接不可达，
  因此额外经 Redis Pub/Sub 转发，由 API 进程的订阅任务转回本地广播。
  未启用 Celery（默认内联执行）时无需 Redis，进程内广播即可生效。
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

REDIS_CHANNEL = "auto_grader:realtime"


class ConnectionManager:
    """按 topic 管理 WebSocket 连接并广播消息。"""

    def __init__(self) -> None:
        self._topics: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, topic: str) -> None:
        async with self._lock:
            self._topics.setdefault(topic, set()).add(websocket)

    async def disconnect(self, websocket: WebSocket, topic: str) -> None:
        async with self._lock:
            subscribers = self._topics.get(topic)
            if subscribers:
                subscribers.discard(websocket)
                if not subscribers:
                    self._topics.pop(topic, None)

    async def disconnect_all(self, websocket: WebSocket) -> None:
        async with self._lock:
            for topic, subscribers in list(self._topics.items()):
                subscribers.discard(websocket)
                if not subscribers:
                    self._topics.pop(topic, None)

    async def broadcast(self, topic: str, message: Dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._topics.get(topic, set()))
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:  # noqa: BLE001  连接已断开
                await self.disconnect(websocket, topic)

    def size(self) -> int:
        return sum(len(s) for s in self._topics.values())


manager = ConnectionManager()

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """在应用启动时绑定主事件循环，供同步业务代码调度广播使用。"""
    global _main_loop
    _main_loop = loop


def _build_message(topic: str, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "topic": topic,
        "type": event_type,
        # 业务数据可能含 UUID / datetime 等，统一转为 JSON 可序列化结构
        "data": _jsonable(data),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _jsonable(value: Any) -> Any:
    """确保 payload 可被 json 序列化（UUID、datetime 等降级为字符串）。"""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return {}


def _redis_publish(message: Dict[str, Any]) -> None:
    """仅在 Celery 模式下，将消息发往 Redis，供 API 进程转回本地广播。"""
    if not settings.USE_CELERY:
        return
    try:
        import redis  # 延迟导入，未安装/未启用时不影响主流程

        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        client.publish(REDIS_CHANNEL, json.dumps(message))
        client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("实时事件 Redis 转发失败: %s", exc)


def publish(topic: str, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    """同步发布事件：本地广播 + （Celery 模式下）Redis 转发。"""
    message = _build_message(topic, event_type, data or {})
    if _main_loop is not None and _main_loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(manager.broadcast(topic, message), _main_loop)
        except Exception as exc:  # noqa: BLE001
            logger.warning("实时事件本地广播失败: %s", exc)
    _redis_publish(message)


def publish_exam_event(exam_id: Any, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    """同时推送到考试专属 topic 与全局 exams topic（供监控看板订阅）。"""
    payload = dict(data or {})
    payload.setdefault("exam_id", str(exam_id))
    publish(f"exam:{exam_id}", event_type, payload)
    publish("exams", event_type, payload)


def publish_user_event(user_id: Any, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    publish(f"user:{user_id}", event_type, data or {})


async def _redis_relay() -> None:
    """订阅 Redis 频道并把消息转回本地广播（仅 Celery 模式需要）。"""
    try:
        import redis.asyncio as aioredis
    except Exception as exc:  # noqa: BLE001
        logger.warning("未安装 redis 客户端，跳过实时中继: %s", exc)
        return

    while True:
        try:
            client = aioredis.from_url(settings.REDIS_URL)
            pubsub = client.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL)
            logger.info("实时事件 Redis 中继已启动")
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                try:
                    message = json.loads(raw["data"])
                    await manager.broadcast(message.get("topic", ""), message)
                except Exception:  # noqa: BLE001
                    continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("实时中继连接异常，5 秒后重试: %s", exc)
            await asyncio.sleep(5)


def start_redis_relay() -> Optional[asyncio.Task]:
    if not settings.USE_CELERY:
        return None
    return asyncio.create_task(_redis_relay())