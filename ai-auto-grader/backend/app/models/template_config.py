import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Numeric, ForeignKey, Integer, JSON, Text
from sqlalchemy.types import Uuid

from app.db.base import Base


class TemplateRegion(Base):
    """模板识别区域：考号区 / 姓名区 / 选择题区 / 非选择题答题框"""

    __tablename__ = "template_regions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(Uuid(as_uuid=True), ForeignKey("answer_card_templates.id"), nullable=False, index=True)
    page_index = Column(Integer, default=0, nullable=False)
    region_type = Column(String(32), nullable=False)  # exam_number / name / choice / subjective
    question_number = Column(String(64), nullable=True)
    sub_question_number = Column(String(64), nullable=True)
    max_score = Column(Numeric(8, 2), default=0)
    x = Column(Numeric(10, 2), default=0, nullable=False)
    y = Column(Numeric(10, 2), default=0, nullable=False)
    width = Column(Numeric(10, 2), default=0, nullable=False)
    height = Column(Numeric(10, 2), default=0, nullable=False)
    options_count = Column(Integer, default=4)
    allow_multiple = Column(Boolean, default=False, nullable=False)
    partial_score_rules = Column(JSON, nullable=True)
    knowledge_tags = Column(JSON, nullable=True)
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ChoiceAnswer(Base):
    """选择题标准答案（按考试配置）"""

    __tablename__ = "choice_answers"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=True, index=True)
    template_id = Column(Uuid(as_uuid=True), ForeignKey("answer_card_templates.id"), nullable=False, index=True)
    question_number = Column(String(64), nullable=False)
    correct_options = Column(String(32), nullable=False)
    score = Column(Numeric(6, 2), default=0)
    partial_score_rules = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AIScoringConfig(Base):
    """非选择题 AI 评分规则配置"""

    __tablename__ = "ai_scoring_configs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=True, index=True)
    template_id = Column(Uuid(as_uuid=True), ForeignKey("answer_card_templates.id"), nullable=False, index=True)
    question_number = Column(String(64), nullable=False)
    standard_answer = Column(Text, nullable=True)
    scoring_points = Column(JSON, nullable=True)
    deduction_notes = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=True)
    confidence_threshold = Column(Numeric(4, 3), default=0.7)
    score_tolerance = Column(Numeric(6, 2), default=0)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))