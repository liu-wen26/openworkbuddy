from uuid import UUID
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class StudentBase(BaseModel):
    exam_number: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    class_name: Optional[str] = Field(default=None, max_length=64)


class StudentCreate(StudentBase):
    pass


class StudentOut(StudentBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class ExamStudentOut(BaseModel):
    id: UUID
    exam_id: UUID
    student_id: UUID
    exam_number: str
    name: str
    class_name: Optional[str]
    is_absent: bool
    total_score: Optional[float]
    rank_in_grade: Optional[int]
    rank_in_class: Optional[int]

    class Config:
        from_attributes = True


class StudentImportResult(BaseModel):
    total: int
    success: int
    failed: int
    errors: List[str]
