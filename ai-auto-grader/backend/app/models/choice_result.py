import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, JSON, Text
from sqlalchemy.types import Uuid

from app.db.base import Base


class ChoiceResult(Base):
    """选择题判分结果：一个选择题区域（题块）对应一条记录"""

    __tablename__ = "choice_results"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    student_id = Column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=True, index=True)
    page_id = Column(Uuid(as_uuid=True), ForeignKey("imported_pages.id"), nullable=False, index=True)
    block_id = Column(Uuid(as_uuid=True), ForeignKey("answer_blocks.id"), nullable=False, index=True)
    region_id = Column(Uuid(as_uuid=True), ForeignKey("template_regions.id"), nullable=False)
    question_number = Column(String(64), nullable=False, index=True)

    recognized_options = Column(String(32), nullable=True)  # 识别结果，如 "AC"；空串表示未填涂
    correct_options = Column(String(32), nullable=True)
    is_correct = Column(Boolean, default=False, nullable=False)
    score = Column(Numeric(6, 2), default=0, nullable=False)
    max_score = Column(Numeric(6, 2), default=0, nullable=False)

    status = Column(String(32), default="scored", nullable=False, index=True)  # scored / exception / reviewed
    exception_type = Column(String(64), nullable=True)  # missing_fill / multi_fill / ambiguous / no_answer_key / unreadable
    confidence = Column(Numeric(4, 3), nullable=True)
    fill_ratios = Column(JSON, nullable=True)  # 各选项填涂占比，便于人工复核

    reviewed_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )