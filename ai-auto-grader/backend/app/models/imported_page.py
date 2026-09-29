import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Numeric, Boolean
from sqlalchemy.types import Uuid

from app.db.base import Base


class ImportedPage(Base):
    """导入的答卷页：PDF 的每一页或上传的每一张图片"""

    __tablename__ = "imported_pages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(Uuid(as_uuid=True), ForeignKey("import_batches.id"), nullable=False, index=True)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)  # pdf / image
    original_file_path = Column(String(512), nullable=False)
    original_page_index = Column(Integer, nullable=True)
    preprocessed_image_path = Column(String(512), nullable=True)
    student_id = Column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=True, index=True)
    exam_number_ocr = Column(String(64), nullable=True)
    tilt_angle = Column(Numeric(6, 2), nullable=True)  # 检测到的倾斜角度
    perspective_corrected = Column(Boolean, default=False, nullable=False)
    status = Column(String(32), default="pending", nullable=False)  # pending / matched / exception / processed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))