"""标注式答题卡底图页服务。

职责：上传真实答题卡（图片 / PDF）作为模板底图，逐页登记真实尺寸、朝向与空白页判定，
并提供画布缩略图、原图访问与框选裁剪预览。

关键约束：
- 原图按上传尺寸原样保存，不做任何缩放/拉伸（坐标使用 0~1000 相对坐标系）；
- PDF 逐页按固定 200 DPI 渲染为图，保证坐标系稳定；
- 页序 = 上传顺序，导入学生答卷时按页序与模板页对齐。
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

import numpy as np
import pymupdf as fitz
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.template import AnswerCardTemplate
from app.models.template_page import TemplatePage
from app.utils import image as image_utils
from app.utils.file_storage import absolute_path, ensure_dir, relative_to_root

logger = logging.getLogger(__name__)
settings = get_settings()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
PDF_EXTENSIONS = {".pdf"}
PDF_ZOOM = 200 / 72  # 约 200 DPI，与答卷导入保持一致
BLANK_INK_THRESHOLD = 0.002  # 墨迹占比低于该值判定为空白页
MAX_PAGES = 20


# ---------------- 目录与查询 ----------------

def _pages_dir(template_id: UUID) -> Path:
    return ensure_dir(Path(settings.STORAGE_ROOT) / "templates" / str(template_id) / "pages")


def _active_pages(db: Session, template_id: UUID) -> List[TemplatePage]:
    return (
        db.query(TemplatePage)
        .filter(TemplatePage.template_id == template_id, TemplatePage.status == "active")
        .order_by(TemplatePage.page_index)
        .all()
    )


def list_pages(db: Session, template_id: UUID) -> List[TemplatePage]:
    return _active_pages(db, template_id)


def get_page(db: Session, template_id: UUID, page_index: int) -> TemplatePage:
    page = (
        db.query(TemplatePage)
        .filter(
            TemplatePage.template_id == template_id,
            TemplatePage.page_index == page_index,
            TemplatePage.status == "active",
        )
        .first()
    )
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="底图页不存在")
    return page


# ---------------- 上传 ----------------

def upload_pages(
    db: Session, template: AnswerCardTemplate, files: List[UploadFile]
) -> Tuple[int, List[TemplatePage]]:
    """上传答题卡底图（可多文件），返回 (新增页数, 新增页列表)。"""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个文件")

    existing = _active_pages(db, template.id)
    next_index = (max((p.page_index for p in existing), default=-1) + 1)
    if next_index >= MAX_PAGES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"底图页数上限为 {MAX_PAGES} 页")

    pages_dir = _pages_dir(template.id)
    created: List[TemplatePage] = []

    for file in files:
        name = (file.filename or "").lower()
        suffix = Path(name).suffix
        if suffix in PDF_EXTENSIONS:
            created.extend(_save_pdf(db, template, file, pages_dir, next_index))
            next_index = max(p.page_index for p in created) + 1
        elif suffix in IMAGE_EXTENSIONS:
            page = _save_image(db, template, file, pages_dir, suffix, next_index)
            created.append(page)
            next_index += 1
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件类型：{file.filename}（仅支持 PDF 与常见图片格式）",
            )

    template.source_type = "annotated"
    db.flush()
    _sync_page_meta(db, template)
    db.commit()
    for page in created:
        db.refresh(page)
    return len(created), created


def _save_image(
    db: Session,
    template: AnswerCardTemplate,
    file: UploadFile,
    pages_dir: Path,
    suffix: str,
    page_index: int,
) -> TemplatePage:
    target = pages_dir / f"page_{page_index}{suffix}"
    file.file.seek(0)
    with open(target, "wb") as f:
        f.write(file.file.read())

    image = image_utils.load_image(target)
    height, width = image.shape[:2]
    blank, ratio = image_utils.is_blank_page(image, BLANK_INK_THRESHOLD)
    thumb_rel = _write_thumb(image, pages_dir / f"thumb_{page_index}.png")

    page = TemplatePage(
        template_id=template.id,
        page_index=page_index,
        source_path=relative_to_root(target),
        thumb_path=thumb_rel,
        width_px=int(width),
        height_px=int(height),
        orientation=image_utils.orientation_of(width, height),
        is_blank=blank,
        blank_ratio=round(ratio, 6),
        status="active",
    )
    db.add(page)
    db.flush()
    return page


def _save_pdf(
    db: Session,
    template: AnswerCardTemplate,
    file: UploadFile,
    pages_dir: Path,
    start_index: int,
) -> List[TemplatePage]:
    raw = pages_dir / f"source_{start_index}.pdf"
    file.file.seek(0)
    with open(raw, "wb") as f:
        f.write(file.file.read())

    try:
        doc = fitz.open(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"PDF 解析失败：{exc}") from exc

    pages: List[TemplatePage] = []
    remaining = max(0, MAX_PAGES - start_index)
    try:
        for offset in range(min(doc.page_count, remaining)):
            page_index = start_index + offset
            image = _render_pdf_page(doc, offset)
            if image is None:
                continue
            target = pages_dir / f"page_{page_index}.png"
            image_utils.save_image(image, target)
            height, width = image.shape[:2]
            blank, ratio = image_utils.is_blank_page(image, BLANK_INK_THRESHOLD)
            thumb_rel = _write_thumb(image, pages_dir / f"thumb_{page_index}.png")

            page = TemplatePage(
                template_id=template.id,
                page_index=page_index,
                source_path=relative_to_root(target),
                thumb_path=thumb_rel,
                width_px=int(width),
                height_px=int(height),
                orientation=image_utils.orientation_of(width, height),
                is_blank=blank,
                blank_ratio=round(ratio, 6),
                status="active",
            )
            db.add(page)
            pages.append(page)
        db.flush()
    finally:
        doc.close()
    return pages


def _render_pdf_page(doc: "fitz.Document", index: int) -> Optional[np.ndarray]:
    try:
        pdf_page = doc.load_page(index)
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(PDF_ZOOM, PDF_ZOOM))
    except Exception as exc:  # noqa: BLE001
        logger.warning("渲染 PDF 第 %s 页失败: %s", index, exc)
        return None
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    if pix.n == 1:
        return img[:, :, 0]
    return img[:, :, ::-1].copy()  # RGB -> BGR


def _write_thumb(image: np.ndarray, target: Path) -> str:
    thumb = image_utils.make_thumbnail(image)
    image_utils.save_image(thumb, target)
    return relative_to_root(target)


# ---------------- 页管理 ----------------

def update_page(
    db: Session,
    template: AnswerCardTemplate,
    page_index: int,
    is_blank: Optional[bool] = None,
) -> TemplatePage:
    page = get_page(db, template.id, page_index)
    if is_blank is not None:
        page.is_blank = is_blank
    db.commit()
    db.refresh(page)
    _sync_page_meta(db, template)
    db.commit()
    return page


def delete_page(db: Session, template: AnswerCardTemplate, page_index: int) -> None:
    """软删除底图页：保留 page_index 稳定，避免影响已框选区域的页码引用。"""
    page = get_page(db, template.id, page_index)
    page.status = "removed"
    db.commit()
    _sync_page_meta(db, template)
    db.commit()


def _sync_page_meta(db: Session, template: AnswerCardTemplate) -> None:
    """把底图页信息回写到模板：页数、真实尺寸列表、朝向。"""
    pages = _active_pages(db, template.id)
    template.page_count = max(1, len(pages))
    template.page_sizes = [
        {
            "page_index": p.page_index,
            "width_px": p.width_px,
            "height_px": p.height_px,
            "orientation": p.orientation,
            "is_blank": p.is_blank,
        }
        for p in pages
    ]
    first = pages[0] if pages else None
    template.orientation = first.orientation if first else "portrait"
    db.flush()


# ---------------- 图像访问与预览 ----------------

def page_image_bytes(db: Session, template_id: UUID, page_index: int, thumb: bool = True) -> Tuple[bytes, str]:
    """返回底图页图像字节与 media type。"""
    page = get_page(db, template_id, page_index)
    rel = page.thumb_path if thumb and page.thumb_path else page.source_path
    path = absolute_path(rel)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="底图文件缺失")
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return path.read_bytes(), media


def crop_preview(
    db: Session,
    template_id: UUID,
    page_index: int,
    x: float,
    y: float,
    width: float,
    height: float,
) -> bytes:
    """按相对坐标从底图裁剪一块并返回 PNG，供前端"所见即所得"核对框选。"""
    page = get_page(db, template_id, page_index)
    path = absolute_path(page.source_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="底图文件缺失")
    image = image_utils.load_image(path)
    crop = image_utils.crop_region(image, x, y, width, height)
    if crop.size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="裁剪区域无效")
    return image_utils.encode_png(crop)


# ---------------- 复制与补印 ----------------

def copy_pages(db: Session, src_template_id: UUID, dst_template_id: UUID) -> None:
    """复制底图页（含文件），保证模板副本仍可继续框选与识别。"""
    src_pages = _active_pages(db, src_template_id)
    if not src_pages:
        return
    dst_dir = _pages_dir(dst_template_id)

    for page in src_pages:
        new_page = TemplatePage(
            template_id=dst_template_id,
            page_index=page.page_index,
            source_path=page.source_path,
            thumb_path=page.thumb_path,
            width_px=page.width_px,
            height_px=page.height_px,
            orientation=page.orientation,
            is_blank=page.is_blank,
            blank_ratio=page.blank_ratio,
            status="active",
        )
        db.add(new_page)
        db.flush()
        for rel in (page.source_path, page.thumb_path):
            if not rel:
                continue
            src_file = absolute_path(rel)
            if src_file.exists():
                target = dst_dir / src_file.name
                shutil.copy2(src_file, target)
                setattr(new_page, "source_path" if rel == page.source_path else "thumb_path", relative_to_root(target))
    db.flush()


def render_annotated_pdf(db: Session, template: AnswerCardTemplate) -> bytes:
    """把标注式模板的底图页合成为 PDF，用于补印空白答题卡。

    页尺寸按 200 DPI 由像素换算为点（px * 72 / 200），保持原始版面比例。
    """
    pages = _active_pages(db, template.id)
    if not pages:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该模板尚未上传答题卡底图")

    doc = fitz.open()
    try:
        for page in pages:
            img_path = absolute_path(page.source_path)
            if not img_path.exists():
                continue
            width_pt = max(1.0, page.width_px * 72.0 / 200.0)
            height_pt = max(1.0, page.height_px * 72.0 / 200.0)
            pdf_page = doc.new_page(width=width_pt, height=height_pt)
            pdf_page.insert_image(fitz.Rect(0, 0, width_pt, height_pt), filename=str(img_path))
        return doc.tobytes()
    finally:
        doc.close()