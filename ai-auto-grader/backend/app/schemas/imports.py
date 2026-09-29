from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ImportBatchCreate(BaseModel):
    exam_id: UUID
    import_type: str = Field(..., pattern=r"^(pdf|image)$")
    source: str = Field(default="formal", pattern=r"^(formal|precheck)$")


class ImportBatchOut(BaseModel):
    id: UUID
    exam_id: UUID
    import_type: str
    status: str
    total_files: int
    total_pages: int
    processed_pages: int
    source: str
    message: Optional[str] = None
    created_by: UUID
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ImportProgressOut(BaseModel):
    batch_id: UUID
    status: str
    total_pages: int
    processed_pages: int
    percent: float
    exception_count: int
    message: Optional[str] = None


class ImportedPageOut(BaseModel):
    id: UUID
    batch_id: UUID
    exam_id: UUID
    source_type: str
    original_file_path: str
    original_page_index: Optional[int] = None
    preprocessed_image_path: Optional[str] = None
    student_id: Optional[UUID] = None
    exam_number_ocr: Optional[str] = None
    tilt_angle: Optional[Decimal] = None
    perspective_corrected: bool
    status: str
    created_at: datetime
    # 关联展示字段
    student_name: Optional[str] = None
    class_name: Optional[str] = None

    class Config:
        from_attributes = True


class AnswerBlockOut(BaseModel):
    id: UUID
    page_id: UUID
    exam_id: UUID
    student_id: Optional[UUID] = None
    region_id: UUID
    question_number: Optional[str] = None
    block_type: str
    image_path: Optional[str] = None
    x: Decimal
    y: Decimal
    width: Decimal
    height: Decimal
    status: str

    class Config:
        from_attributes = True


class ExceptionOut(BaseModel):
    id: UUID
    exam_id: UUID
    page_id: Optional[UUID] = None
    block_id: Optional[UUID] = None
    exception_type: str
    source: str
    status: str
    description: Optional[str] = None
    snapshot_path: Optional[str] = None
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    resolution_action: Optional[str] = None
    resolution_note: Optional[str] = None
    created_at: datetime
    # 关联展示字段
    exam_number_ocr: Optional[str] = None
    student_name: Optional[str] = None

    class Config:
        from_attributes = True


class ExceptionUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(resolved|ignored|pending)$")
    resolution_action: Optional[str] = None
    resolution_note: Optional[str] = None


class ManualExamNumberIn(BaseModel):
    exam_number: str = Field(..., min_length=1, max_length=64)


class RecutIn(BaseModel):
    perspective_points: Optional[List[List[float]]] = None


class ImportUploadResult(BaseModel):
    batch: ImportBatchOut
    pages: List[ImportedPageOut]
    mode: str


# ---------------- 分片上传 ----------------

class ChunkUploadInitIn(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    total_size: int = Field(..., gt=0)
    chunk_size: Optional[int] = Field(default=None, gt=0)


class ChunkUploadStatusOut(BaseModel):
    upload_id: str
    filename: str
    total_size: int
    chunk_size: int
    total_chunks: int
    received: List[int] = []
    completed: bool = False