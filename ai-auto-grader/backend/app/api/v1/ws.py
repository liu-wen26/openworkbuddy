"""实时推送 WebSocket 端点（阶段 9）。

客户端通过 `?token=<JWT>` 连接；连接后默认订阅个人 topic `user:<user_id>`，
可再发送 {"action":"subscribe","topic":"exam:<id>"} 订阅考试进度等业务事件。
服务端推送消息格式：{"topic", "type", "data", "ts"}。
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.db.base import SessionLocal
from app.models.user import User
from app.services import realtime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Realtime"])


def _authenticate(token: str) -> User | None:
    payload = decode_token(token)
    if not payload or not payload.sub:
        return None
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.id == UUID(str(payload.sub))).first()
        if user and user.is_active:
            return user
        return None
    except (ValueError, TypeError):
        return None
    finally:
        session.close()


@router.websocket("/ws")
async def realtime_ws(websocket: WebSocket, token: str = Query(default="")):
    user = _authenticate(token)
    if not user:
        # 未认证：拒绝握手
        await websocket.close(code=4001)
        return

    await websocket.accept()
    personal_topic = f"user:{user.id}"
    await realtime.manager.connect(websocket, personal_topic)
    subscribed = {personal_topic}
    await websocket.send_json({
        "topic": personal_topic,
        "type": "connected",
        "data": {"user_id": str(user.id)},
    })

    try:
        while True:
            message = await websocket.receive_json()
            action = (message or {}).get("action")
            topic = (message or {}).get("topic")
            if action == "ping":
                await websocket.send_json({"type": "pong", "data": {}})
            elif action == "subscribe" and topic:
                await realtime.manager.connect(websocket, topic)
                subscribed.add(topic)
            elif action == "unsubscribe" and topic:
                await realtime.manager.disconnect(websocket, topic)
                subscribed.discard(topic)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("WebSocket 异常关闭: %s", exc)
    finally:
        for topic in subscribed:
            await realtime.manager.disconnect(websocket, topic)