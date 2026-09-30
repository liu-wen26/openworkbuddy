import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, JSON, BigInteger, ForeignKey
from sqlalchemy.types import Uuid

from app.db.base import Base


class ExamArchive(Base):
    """考试归档记录（F10-04）。

    归档会把考试标记为 archived，并把原试卷+成绩导出打包到归档目录；
    恢复时还原考试状态，删除时移除归档记录与打包文件。
    """

    __tablename__ = "exam_archives"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    exam_name = Column(String(255), nullable=False)
    previous_status = Column(String(32), nullable=True)
    status = Column(String(32), default="archived", nullable=False, index=True)  # archived / restored
    bundle_path = Column(String(512), nullable=True)
    file_size = Column(BigInteger, default=0, nullable=False)
    original_paper_included = Column(Boolean, default=False, nullable=False)
    snapshot = Column(JSON, nullable=True)  # 归档时的统计数据快照
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    restored_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    restored_at = Column(DateTime(timezone=True), nullable=True)