import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.types import Uuid

from app.db.base import Base


class ImportBatch(Base):
    """答卷导入批次：一次导入上传的多个 PDF / 图片文件归为一个批次"""

    __tablename__ = "import_batches"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    import_type = Column(String(32), nullable=False)  # pdf / image
    status = Column(String(32), default="pending", nullable=False)  # pending / processing / completed / failed
    total_files = Column(Integer, default=0, nullable=False)
    total_pages = Column(Integer, default=0, nullable=False)
    processed_pages = Column(Integer, default=0, nullable=False)
    source = Column(String(32), default="formal", nullable=False)  # formal / precheck
    message = Column(Text, nullable=True)  # 失败原因或处理说明
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)