import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, JSON, Numeric
from sqlalchemy.types import Uuid

from app.db.base import Base


class PrecheckSession(Base):
    """预阅卷会话：正式导入前，用少量样卷测试模板与 AI 效果。

    预阅卷数据与正式数据完全隔离：不写入 answer_blocks / choice_results /
    subjective_results / exam_exceptions，仅在本表与 precheck_pages 中留快照。
    """

    __tablename__ = "precheck_sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    status = Column(String(32), default="active", nullable=False, index=True)  # active / cleared
    sample_count = Column(Integer, default=0, nullable=False)
    page_count = Column(Integer, default=0, nullable=False)
    message = Column(String(512), nullable=True)
    summary = Column(JSON, nullable=True)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    cleared_at = Column(DateTime(timezone=True), nullable=True)


class PrecheckPage(Base):
    """预阅卷样卷页：保存单个样卷页的预处理图与切割 / OMR / AI 快照。"""

    __tablename__ = "precheck_pages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(Uuid(as_uuid=True), ForeignKey("precheck_sessions.id"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)  # pdf / image
    original_file_path = Column(String(512), nullable=False)
    original_page_index = Column(Integer, nullable=True)
    preprocessed_image_path = Column(String(512), nullable=True)
    exam_number_ocr = Column(String(64), nullable=True)
    name_ocr = Column(String(64), nullable=True)   # 视觉识别的姓名（用于按姓名兜底匹配）
    class_ocr = Column(String(64), nullable=True)  # 视觉识别的班级
    tilt_angle = Column(Numeric(6, 2), nullable=True)
    status = Column(String(32), default="pending", nullable=False)  # pending / processed / exception

    cut_result = Column(JSON, nullable=True)  # 切割结果快照
    omr_result = Column(JSON, nullable=True)  # 选择题识别快照
    ai_result = Column(JSON, nullable=True)   # 非选择题 AI 评分快照

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))