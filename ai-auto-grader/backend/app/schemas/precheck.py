from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class PrecheckSessionCreate(BaseModel):
    exam_id: UUID


class PrecheckPageOut(BaseModel):
    id: UUID
    session_id: UUID
    source_type: str
    original_page_index: Optional[int] = None
    preprocessed_image_path: Optional[str] = None
    exam_number_ocr: Optional[str] = None
    tilt_angle: Optional[float] = None
    status: str
    cut_result: Optional[List[Dict[str, Any]]] = None
    omr_result: Optional[List[Dict[str, Any]]] = None
    ai_result: Optional[List[Dict[str, Any]]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PrecheckSessionOut(BaseModel):
    id: UUID
    exam_id: UUID
    status: str
    sample_count: int
    page_count: int
    message: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    cleared_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PrecheckSessionDetailOut(PrecheckSessionOut):
    pages: List[PrecheckPageOut] = []


class PrecheckUploadResult(BaseModel):
    session: PrecheckSessionOut
    added: int
    pages: List[PrecheckPageOut]


class PrecheckClearOut(BaseModel):
    session_id: UUID
    status: str
    cleared_pages: int
    cleared_samples: int