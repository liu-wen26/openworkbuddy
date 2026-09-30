from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GradingTaskOut(BaseModel):
    id: UUID
    exam_id: UUID
    student_id: Optional[UUID] = None
    page_id: UUID
    block_id: UUID
    region_id: UUID
    question_number: Optional[str] = None
    max_score: float

    grading_mode: str
    status: str

    ai_score: Optional[float] = None
    ai_comment: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_model: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_scored_at: Optional[datetime] = None

    first_score: Optional[float] = None
    first_comment: Optional[str] = None
    first_grader_id: Optional[UUID] = None
    first_graded_at: Optional[datetime] = None

    second_score: Optional[float] = None
    second_comment: Optional[str] = None
    second_grader_id: Optional[UUID] = None
    second_graded_at: Optional[datetime] = None

    final_score: Optional[float] = None
    arbiter_id: Optional[UUID] = None
    arbitrated_at: Optional[datetime] = None
    arbitration_note: Optional[str] = None

    mark: str = "none"
    assigned_to: Optional[UUID] = None
    assigned_at: Optional[datetime] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    # 关联展示字段
    exam_number: Optional[str] = None
    student_name: Optional[str] = None
    class_name: Optional[str] = None

    class Config:
        from_attributes = True


class GradingGradeIn(BaseModel):
    score: float
    comment: Optional[str] = None
    mark: Optional[str] = Field(default=None, description="none / excellent / typical_error / blank")


class GradingArbitrateIn(BaseModel):
    final_score: float
    note: Optional[str] = None


class GradingDistributeIn(BaseModel):
    mode: str = Field(description="manual / ai_assist / double")
    assign_to: Optional[UUID] = None
    question_numbers: Optional[List[str]] = None


class GradingDistributeOut(BaseModel):
    mode: str
    assigned: int


class GradingAIScoreOut(BaseModel):
    scored: int
    low_confidence: int
    skipped: int
    failed: int
    provider: str


class GradingQuestionProgress(BaseModel):
    question_number: str
    total: int
    graded: int
    arbitrating: int
    ai_scored: int = 0
    max_score: float


class GradingProgressOut(BaseModel):
    total: int
    done: int
    completion_rate: float
    by_status: Dict[str, int]
    by_question: List[GradingQuestionProgress]
    ai_scored: int = 0
    ai_pending_review: int = 0
    ai_pending_rate: float = 0.0
    finished_rate: float = 0.0


class GradingLogOut(BaseModel):
    id: UUID
    exam_id: UUID
    block_id: Optional[UUID] = None
    result_id: Optional[UUID] = None
    action: str
    operator_id: Optional[UUID] = None
    operator_name: Optional[str] = None
    score_before: Optional[float] = None
    score_after: Optional[float] = None
    note: Optional[str] = None
    detail: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True