from typing import Dict, List, Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ChoiceResultOut(BaseModel):
    id: UUID
    exam_id: UUID
    student_id: Optional[UUID] = None
    page_id: UUID
    block_id: UUID
    region_id: UUID
    question_number: str
    recognized_options: Optional[str] = None
    correct_options: Optional[str] = None
    is_correct: bool
    score: Decimal
    max_score: Decimal
    status: str
    exception_type: Optional[str] = None
    confidence: Optional[Decimal] = None
    fill_ratios: Optional[List[float]] = None
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # 关联展示字段
    exam_number: Optional[str] = None
    student_name: Optional[str] = None
    class_name: Optional[str] = None

    class Config:
        from_attributes = True


class ChoiceReviewIn(BaseModel):
    options: str = Field(default="", max_length=32, description="复核后的选项，如 'AC'；空串表示未填涂")
    note: Optional[str] = None


class ChoiceGradeOut(BaseModel):
    graded: int
    scored: int
    exception: int
    skipped: int


class ChoiceOverallStat(BaseModel):
    total_questions: int
    total_results: int
    graded: int
    exception: int
    reviewed: int
    correct: int
    correct_rate: float
    avg_score: float


class ChoiceQuestionStat(BaseModel):
    question_number: str
    options_count: int
    allow_multiple: bool
    max_score: float
    total: int
    graded: int
    correct: int
    exception: int
    correct_rate: float
    avg_score: float
    distribution: Dict[str, int]


class ChoiceStatisticsOut(BaseModel):
    overall: ChoiceOverallStat
    questions: List[ChoiceQuestionStat]


class ChoiceAnswerItem(BaseModel):
    question_number: str
    options_count: int
    allow_multiple: bool
    max_score: float
    correct_options: str = ""
    score: float = 0
    source: str = "none"  # exam / template / none


class ChoiceAnswerListOut(BaseModel):
    template_id: UUID
    items: List[ChoiceAnswerItem]


class ChoiceAnswerIn(BaseModel):
    question_number: str = Field(max_length=64)
    correct_options: str = Field(default="", max_length=32)
    score: Optional[float] = None


class ChoiceAnswerSaveIn(BaseModel):
    items: List[ChoiceAnswerIn] = Field(default_factory=list)
    regrade: bool = True


class ChoiceAnswerSaveOut(BaseModel):
    template_id: UUID
    items: List[ChoiceAnswerItem]
    grade: Optional[ChoiceGradeOut] = None