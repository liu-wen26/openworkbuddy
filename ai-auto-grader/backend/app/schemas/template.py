from uuid import UUID
from datetime import datetime
from typing import Optional, List, Any, Dict
from decimal import Decimal

from pydantic import BaseModel, Field


class TemplateRegionBase(BaseModel):
    page_index: int = 0
    region_type: str = Field(..., pattern=r"^(exam_number|name|choice|subjective)$")
    question_number: Optional[str] = None
    sub_question_number: Optional[str] = None
    max_score: Decimal = Decimal("0")
    x: Decimal = Decimal("0")
    y: Decimal = Decimal("0")
    width: Decimal = Decimal("0")
    height: Decimal = Decimal("0")
    options_count: int = 4
    allow_multiple: bool = False
    partial_score_rules: Optional[Any] = None
    knowledge_tags: Optional[Any] = None
    config: Optional[Dict[str, Any]] = None


class TemplateRegionCreate(TemplateRegionBase):
    pass


class TemplateRegionOut(TemplateRegionBase):
    id: UUID
    template_id: UUID

    class Config:
        from_attributes = True


class TemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    subject: Optional[str] = None
    paper_size: str = Field(default="A4", pattern=r"^(A3|A4)$")
    duplex: bool = False
    page_count: int = 1
    margin_top: Decimal = Decimal("10")
    margin_bottom: Decimal = Decimal("10")
    margin_left: Decimal = Decimal("10")
    margin_right: Decimal = Decimal("10")
    title: str = "答题卡"
    exam_number_digits: int = 9
    exam_number_mode: str = Field(default="omr", pattern=r"^(omr|ocr)$")
    class_prefix_enabled: bool = False
    name_ocr_enabled: bool = False
    tilt_threshold: Decimal = Decimal("5")
    perspective_enabled: bool = True
    deskew_enabled: bool = True
    description: Optional[str] = None


class TemplateCreate(TemplateBase):
    regions: Optional[List[TemplateRegionCreate]] = None


class TemplateUpdate(TemplateBase):
    pass


class TemplateOut(TemplateBase):
    id: UUID
    is_blank: bool
    source_pdf_path: Optional[str] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TemplateDetailOut(TemplateOut):
    regions: List[TemplateRegionOut] = []


class TemplateCopyRequest(BaseModel):
    name: Optional[str] = None


class ChoiceAnswerBase(BaseModel):
    question_number: str
    correct_options: str
    score: Decimal = Decimal("0")
    partial_score_rules: Optional[Any] = None


class ChoiceAnswerOut(ChoiceAnswerBase):
    id: UUID
    template_id: UUID
    exam_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class ChoiceAnswerBatch(BaseModel):
    answers: List[ChoiceAnswerBase]


class AIScoringConfigBase(BaseModel):
    question_number: str
    standard_answer: Optional[str] = None
    scoring_points: Optional[Any] = None
    deduction_notes: Optional[str] = None
    prompt_template: Optional[str] = None
    confidence_threshold: Decimal = Decimal("0.7")
    score_tolerance: Decimal = Decimal("0")
    enabled: bool = True


class AIScoringConfigOut(AIScoringConfigBase):
    id: UUID
    template_id: UUID
    exam_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class AIScoringConfigBatch(BaseModel):
    configs: List[AIScoringConfigBase]


class TemplateImportRequest(BaseModel):
    payload: Dict[str, Any]


class PrecheckIssue(BaseModel):
    level: str = Field(..., pattern=r"^(error|warning)$")
    code: str
    message: str
    page_index: Optional[int] = None
    region_index: Optional[int] = None


class PrecheckResult(BaseModel):
    passed: bool
    error_count: int
    warning_count: int
    issues: List[PrecheckIssue]