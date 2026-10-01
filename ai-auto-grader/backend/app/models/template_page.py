import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.types import Uuid

from app.db.base import Base


class TemplatePage(Base):
    """答题卡模板底图页：上传的真实答题卡每一页（图片或 PDF 的一页）。

    标注式模板不再由系统绘制卡面，而是以上传的真实答题卡为底图，
    因此需要逐页记录真实像素尺寸、朝向与是否为空白页。
    坐标仍统一使用 0~1000 相对坐标系，导入切割时不重采样，保持原卡尺寸。
    """

    __tablename__ = "template_pages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(Uuid(as_uuid=True), ForeignKey("answer_card_templates.id"), nullable=False, index=True)
    page_index = Column(Integer, nullable=False, default=0)
    source_path = Column(String(512), nullable=False)  # 原图（按上传尺寸原样保存）
    thumb_path = Column(String(512), nullable=True)  # 画布展示用缩略图（不参与识别）
    width_px = Column(Integer, default=0, nullable=False)
    height_px = Column(Integer, default=0, nullable=False)
    orientation = Column(String(16), default="portrait", nullable=False)  # portrait / landscape
    is_blank = Column(Boolean, default=False, nullable=False)  # 是否判定为空白页（可人工覆盖）
    blank_ratio = Column(Numeric(8, 6), nullable=True)  # 墨迹占比，用于空白页判定
    status = Column(String(16), default="active", nullable=False)  # active / removed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))