import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Numeric, ForeignKey, Integer
from sqlalchemy.types import Uuid
from sqlalchemy.orm import relationship

from app.db.base import Base


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    subject = Column(String(64), nullable=False)
    grade = Column(String(64), nullable=False)
    exam_type = Column(String(64), nullable=False)
    total_score = Column(Numeric(8, 2), nullable=False)
    pass_score = Column(Numeric(8, 2), nullable=True)
    excellent_score = Column(Numeric(8, 2), nullable=True)

    answer_card_template_id = Column(Uuid(as_uuid=True), ForeignKey("answer_card_templates.id"), nullable=True)
    original_paper_path = Column(String(512), nullable=True)
    original_paper_uploaded_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    original_paper_uploaded_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(String(32), default="draft", nullable=False)
    grading_start_at = Column(DateTime(timezone=True), nullable=True)
    grading_end_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    template = relationship("AnswerCardTemplate", foreign_keys=[answer_card_template_id])
    created_by_user = relationship("User", foreign_keys=[created_by])


class ExamTeacher(Base):
    __tablename__ = "exam_teachers"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False)
    teacher_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_in_exam = Column(String(32), default="grader", nullable=False)
    assigned_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
