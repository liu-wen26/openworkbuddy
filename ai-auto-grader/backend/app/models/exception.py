import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.types import Uuid

from app.db.base import Base


# 异常类型枚举（与设计文档保持一致）
EXCEPTION_TYPES = [
    "exam_number_not_found",   # 考号识别失败
    "exam_number_not_match",   # 考号不在花名册
    "tilt_exceed",             # 倾斜角度超限
    "perspective_exceed",      # 透视矫正超限
    "cut_failed",              # 题块切割失败
    "choice_multi",            # 选择题多涂
    "choice_blank",            # 选择题漏涂
    "choice_fuzzy",            # 选择题填涂模糊
    "ai_low_confidence",       # AI 低置信度
    "manual_review",           # 人工标记复核
]


class ExamException(Base):
    """全局异常中心记录"""

    __tablename__ = "exceptions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    page_id = Column(Uuid(as_uuid=True), ForeignKey("imported_pages.id"), nullable=True, index=True)
    block_id = Column(Uuid(as_uuid=True), ForeignKey("answer_blocks.id"), nullable=True, index=True)
    exception_type = Column(String(64), nullable=False, index=True)
    source = Column(String(32), default="pdf", nullable=False)  # pdf / image
    status = Column(String(32), default="pending", nullable=False, index=True)  # pending / resolved / ignored
    description = Column(Text, nullable=True)
    snapshot_path = Column(String(512), nullable=True)
    resolved_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_action = Column(String(64), nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))