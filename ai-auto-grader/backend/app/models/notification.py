import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.types import Uuid
from sqlalchemy import JSON

from app.db.base import Base


class Notification(Base):
    """站内消息（F11-04 通知闭环）。

    由 notification_service 在关键业务事件发生时按用户投递，前端顶栏消息中心消费。
    """

    __tablename__ = "notifications"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    event = Column(String(64), nullable=False, index=True)  # grading_assigned / import_finished ...
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    level = Column(String(16), default="info", nullable=False)  # info / success / warning / danger
    link = Column(String(255), nullable=True)  # 前端路由跳转地址
    actor_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    meta = Column(JSON, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)