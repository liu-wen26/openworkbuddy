import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.types import Uuid

from app.db.base import Base


class AnswerBlock(Base):
    """题块：按模板区域从答卷页切割出的单个题目图像"""

    __tablename__ = "answer_blocks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id = Column(Uuid(as_uuid=True), ForeignKey("imported_pages.id"), nullable=False, index=True)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    student_id = Column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=True, index=True)
    region_id = Column(Uuid(as_uuid=True), ForeignKey("template_regions.id"), nullable=False)
    question_number = Column(String(64), nullable=True)
    block_type = Column(String(32), nullable=False)  # choice / subjective / exam_number / name
    image_path = Column(String(512), nullable=True)
    x = Column(Numeric(10, 2), nullable=False)
    y = Column(Numeric(10, 2), nullable=False)
    width = Column(Numeric(10, 2), nullable=False)
    height = Column(Numeric(10, 2), nullable=False)
    status = Column(String(32), default="pending", nullable=False)  # pending / scored / exception / arbitrated
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))