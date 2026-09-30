import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, JSON
from sqlalchemy.types import Uuid

from app.db.base import Base


class AuditLog(Base):
    """操作审计日志（F9-03）。

    记录所有对系统的写操作（POST/PUT/PATCH/DELETE），以及需要显式登记的
    关键业务动作（导出、归档、权限变更等）。
    """

    __tablename__ = "audit_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    username = Column(String(64), nullable=True)
    role = Column(String(32), nullable=True)
    action = Column(String(64), nullable=False, index=True)  # create / update / delete / export / archive / login ...
    method = Column(String(8), nullable=True)
    path = Column(String(255), nullable=True, index=True)
    resource_type = Column(String(64), nullable=True)
    status_code = Column(Integer, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)