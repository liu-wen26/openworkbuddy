import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, JSON, Text
from sqlalchemy.types import Uuid

from app.db.base import Base


# 阅卷模式：仅人工 / AI预评+复核 / 双评
GRADING_MODES = ["manual", "ai_assist", "double"]

# 结果状态流转：
# pending（待阅）→ ai_scored（AI已预评）→ graded（人工已评）
#   双评：graded_pending_second（一评完成待二评）→ arbitrating（差值超限待仲裁）→ arbitrated（已仲裁）
SUBJECTIVE_STATUS = [
    "pending",
    "ai_scored",
    "graded",
    "graded_pending_second",
    "arbitrating",
    "arbitrated",
]

# 作答标记：优秀 / 典型错误 / 空白
ANSWER_MARKS = ["none", "excellent", "typical_error", "blank"]


class SubjectiveResult(Base):
    """非选择题评分结果：AI 预评、人工一评/二评、仲裁与作答标记"""

    __tablename__ = "subjective_results"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    student_id = Column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=True, index=True)
    page_id = Column(Uuid(as_uuid=True), ForeignKey("imported_pages.id"), nullable=False, index=True)
    block_id = Column(Uuid(as_uuid=True), ForeignKey("answer_blocks.id"), nullable=False, index=True)
    region_id = Column(Uuid(as_uuid=True), ForeignKey("template_regions.id"), nullable=False)
    question_number = Column(String(64), nullable=True, index=True)
    max_score = Column(Numeric(6, 2), default=0, nullable=False)

    grading_mode = Column(String(32), default="manual", nullable=False)
    status = Column(String(32), default="pending", nullable=False, index=True)

    # AI 预评
    ai_score = Column(Numeric(6, 2), nullable=True)
    ai_comment = Column(Text, nullable=True)
    ai_confidence = Column(Numeric(4, 3), nullable=True)
    ai_model = Column(String(128), nullable=True)
    ai_provider = Column(String(32), nullable=True)
    ai_detail = Column(JSON, nullable=True)
    ai_scored_at = Column(DateTime(timezone=True), nullable=True)

    # 人工一评
    first_score = Column(Numeric(6, 2), nullable=True)
    first_comment = Column(Text, nullable=True)
    first_grader_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    first_graded_at = Column(DateTime(timezone=True), nullable=True)

    # 人工二评（双评模式）
    second_score = Column(Numeric(6, 2), nullable=True)
    second_comment = Column(Text, nullable=True)
    second_grader_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    second_graded_at = Column(DateTime(timezone=True), nullable=True)

    # 仲裁
    final_score = Column(Numeric(6, 2), nullable=True)
    arbiter_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    arbitrated_at = Column(DateTime(timezone=True), nullable=True)
    arbitration_note = Column(Text, nullable=True)

    mark = Column(String(32), default="none", nullable=False)  # 作答标记
    assigned_to = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GradingLog(Base):
    """阅卷痕迹日志：记录分发、AI 预评、人工评分、仲裁、标记等全部操作"""

    __tablename__ = "grading_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    block_id = Column(Uuid(as_uuid=True), ForeignKey("answer_blocks.id"), nullable=True, index=True)
    result_id = Column(Uuid(as_uuid=True), ForeignKey("subjective_results.id"), nullable=True, index=True)
    question_number = Column(String(64), nullable=True)
    action = Column(String(32), nullable=False)  # distribute / ai_score / grade_first / grade_second / arbitrate / mark
    operator_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    operator_name = Column(String(64), nullable=True)
    score_before = Column(Numeric(6, 2), nullable=True)
    score_after = Column(Numeric(6, 2), nullable=True)
    note = Column(Text, nullable=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))