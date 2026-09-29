from uuid import UUID
from datetime import datetime
from typing import Optional, List
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ExamBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    subject: str = Field(..., min_length=1, max_length=64)
    grade: str = Field(..., min_length=1, max_length=64)
    exam_type: str = Field(..., pattern=r"^(weekly|monthly|midterm|final|mock)$")
    total_score: Decimal = Field(..., gt=0)
    pass_score: Optional[Decimal] = None
    excellent_score: Optional[Decimal] = None
    answer_card_template_id: Optional[UUID] = None
    grading_start_at: Optional[datetime] = None
    grading_end_at: Optional[datetime] = None


class ExamCreate(ExamBase):
    @field_validator("pass_score", "excellent_score", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        if v == "" or v == "null":
            return None
        return v


class ExamUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    exam_type: Optional[str] = None
    total_score: Optional[Decimal] = None
    pass_score: Optional[Decimal] = None
    excellent_score: Optional[Decimal] = None
    answer_card_template_id: Optional[UUID] = None
    grading_start_at: Optional[datetime] = None
    grading_end_at: Optional[datetime] = None


class ExamOut(ExamBase):
    id: UUID
    status: str
    original_paper_path: Optional[str] = None
    original_paper_uploaded_by: Optional[UUID] = None
    original_paper_uploaded_at: Optional[datetime] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExamTeacherAssign(BaseModel):
    teacher_id: UUID
    role_in_exam: str = Field(default="grader", pattern=r"^(grader|leader)$")


class ExamTeachersUpdate(BaseModel):
    teachers: List[ExamTeacherAssign]


class ExamOriginalPaperOut(BaseModel):
    original_paper_path: Optional[str]
    original_paper_uploaded_by: Optional[UUID]
    original_paper_uploaded_at: Optional[datetime]
