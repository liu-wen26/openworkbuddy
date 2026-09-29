import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class AnswerCardTemplate(Base):
    __tablename__ = "answer_card_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    paper_size = Column(String(16), default="A4", nullable=False)
    duplex = Column(Boolean, default=False, nullable=False)
    margin_top = Column(Numeric(6, 2), default=10)
    margin_bottom = Column(Numeric(6, 2), default=10)
    margin_left = Column(Numeric(6, 2), default=10)
    margin_right = Column(Numeric(6, 2), default=10)
    title = Column(String(255), default="答题卡", nullable=False)
    source_pdf_path = Column(String(512), nullable=True)
    is_blank = Column(Boolean, default=True, nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
