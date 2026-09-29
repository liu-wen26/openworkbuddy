import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Integer, JSON
from sqlalchemy.types import Uuid

from app.db.base import Base


class AnswerCardTemplate(Base):
    __tablename__ = "answer_card_templates"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    subject = Column(String(64), nullable=True)
    paper_size = Column(String(16), default="A4", nullable=False)
    duplex = Column(Boolean, default=False, nullable=False)
    page_count = Column(Integer, default=1, nullable=False)
    margin_top = Column(Numeric(6, 2), default=10)
    margin_bottom = Column(Numeric(6, 2), default=10)
    margin_left = Column(Numeric(6, 2), default=10)
    margin_right = Column(Numeric(6, 2), default=10)
    title = Column(String(255), default="答题卡", nullable=False)
    exam_number_digits = Column(Integer, default=9)
    exam_number_mode = Column(String(16), default="omr")  # omr / ocr
    class_prefix_enabled = Column(Boolean, default=False, nullable=False)
    name_ocr_enabled = Column(Boolean, default=False, nullable=False)
    tilt_threshold = Column(Numeric(6, 2), default=5)
    perspective_enabled = Column(Boolean, default=True, nullable=False)
    deskew_enabled = Column(Boolean, default=True, nullable=False)
    source_pdf_path = Column(String(512), nullable=True)
    is_blank = Column(Boolean, default=True, nullable=False)
    description = Column(String(512), nullable=True)
    created_by = Column(Uuid(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))