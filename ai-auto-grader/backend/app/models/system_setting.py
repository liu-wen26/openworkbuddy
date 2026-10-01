import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, JSON, UniqueConstraint
from sqlalchemy.types import Uuid

from app.db.base import Base


class SystemSetting(Base):
    """系统级配置键值存储（F11：大模型、水印、通知，以及各模块的运行时配置）。

    value 统一存 JSON，便于承载结构化配置；未写入的键回落到代码内默认值。
    """

    __tablename__ = "system_settings"

    key = Column(String(128), primary_key=True)
    value = Column(JSON, nullable=True)
    updated_by = Column(Uuid(as_uuid=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RolePermission(Base):
    """角色权限覆盖（F9-01 角色权限精细化管理）。

    仅存与内置默认权限的差异：allowed=True 表示额外授予，False 表示显式禁用。
    """

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role", "permission", name="uq_role_permission"),)

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(32), nullable=False, index=True)
    permission = Column(String(64), nullable=False)
    allowed = Column(Boolean, default=True, nullable=False)
    updated_by = Column(Uuid(as_uuid=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )