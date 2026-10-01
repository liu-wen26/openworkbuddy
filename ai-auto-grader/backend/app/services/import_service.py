"""答卷导入与预处理服务：负责批次创建、文件接收、PDF 转图、预处理、考号识别匹配、
题块切割以及异常生成。处理流水线被 Celery 任务与内联后台任务共用。
"""

import json
import logging
import math
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

import numpy as np
import pymupdf as fitz
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import SessionLocal
from app.models.answer_block import AnswerBlock
from app.models.exam import Exam
from app.models.exception import ExamException
from app.models.import_batch import ImportBatch
from app.models.imported_page import ImportedPage
from app.models.student import ExamStudent, Student
from app.models.template import AnswerCardTemplate
from app.models.template_config import TemplateRegion
from app.utils import image as image_utils
from app.utils import omr
from app.utils.file_storage import (
    absolute_path,
    ensure_dir,
    get_batch_dir,
    relative_to_root,
    save_upload_to,
)
from app.services.template_service import PAPER_SIZES
from app.services.exam_service import check_exam_modifiable
from app.services import choice_grid_service, notification_service, realtime

logger = logging.getLogger(__name__)
settings = get_settings()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
PDF_ZOOM = 200 / 72  # 约 200 DPI

# 与 template_service 渲染答题卡考号区时保持一致的布局常量（单位 pt）
EXAM_NUMBER_GRID = {
    "start_x": 12.0,
    "start_y": 26.0,
    "col_width": 16.0,
    "row_step": 12.0,
    "bubble_radius": 4.0,
}


# ---------------- 批次创建与文件上传 ----------------

def get_exam_or_404(db: Session, exam_id: UUID) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


def get_batch_or_404(db: Session, batch_id: UUID) -> ImportBatch:
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入批次不存在")
    return batch


def check_batch_exam_modifiable(db: Session, batch: ImportBatch) -> Exam:
    """锁定/归档考试禁止继续写入答卷（与花名册导入口径一致）。"""
    exam = get_exam_or_404(db, batch.exam_id)
    check_exam_modifiable(exam)
    return exam


def create_batch(
    db: Session, exam_id: UUID, import_type: str, source: str, user_id: UUID
) -> ImportBatch:
    exam = get_exam_or_404(db, exam_id)
    check_exam_modifiable(exam)
    if import_type not in ("pdf", "image"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="导入方式仅支持 pdf / image")
    if not exam.answer_card_template_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该考试尚未绑定答题卡模板")

    batch = ImportBatch(
        exam_id=exam_id,
        import_type=import_type,
        source=source or "formal",
        created_by=user_id,
        status="pending",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def save_files(db: Session, batch: ImportBatch, files: List[UploadFile]) -> List[ImportedPage]:
    """保存上传的 PDF / 图片 / zip 图片包，并登记答卷页。"""
    check_batch_exam_modifiable(db, batch)
    source_sub = "source_pdfs" if batch.import_type == "pdf" else "source_images"
    source_dir = get_batch_dir(batch.exam_id, batch.id, source_sub)

    accepted = 0
    for file in files:
        filename = file.filename or "upload"
        suffix = Path(filename).suffix.lower()
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        rel_path = save_upload_to(file, source_dir, stored_name)

        if not _accept_saved_file(db, batch, rel_path, filename):
            continue
        accepted += 1

    batch.total_files += accepted
    db.flush()
    batch.total_pages = db.query(ImportedPage).filter(ImportedPage.batch_id == batch.id).count()
    db.commit()
    db.refresh(batch)
    return db.query(ImportedPage).filter(ImportedPage.batch_id == batch.id).all()


def _accept_saved_file(db: Session, batch: ImportBatch, rel_path: str, original_name: str) -> bool:
    """登记一个已落盘的文件为答卷页。返回是否被接受。"""
    suffix = Path(rel_path).suffix.lower()
    if batch.import_type == "pdf":
        if suffix != ".pdf":
            return False
        _register_pdf_pages(db, batch, rel_path)
        return True

    if suffix == ".zip":
        _extract_zip_images(db, batch, rel_path, absolute_path(rel_path).parent)
        return True
    if suffix in IMAGE_EXTENSIONS:
        _register_image_page(db, batch, rel_path, original_name)
        return True
    return False


def _register_pdf_pages(db: Session, batch: ImportBatch, rel_path: str) -> None:
    full_path = absolute_path(rel_path)
    try:
        doc = fitz.open(full_path)
        page_count = doc.page_count
        doc.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("无法解析 PDF %s: %s", rel_path, exc)
        page_count = 1

    for page_index in range(page_count):
        db.add(ImportedPage(
            batch_id=batch.id,
            exam_id=batch.exam_id,
            source_type="pdf",
            original_file_path=rel_path,
            original_page_index=page_index,
            status="pending",
        ))


def _register_image_page(db: Session, batch: ImportBatch, rel_path: str, original_name: str) -> None:
    db.add(ImportedPage(
        batch_id=batch.id,
        exam_id=batch.exam_id,
        source_type="image",
        original_file_path=rel_path,
        original_page_index=0,
        status="pending",
    ))


def _extract_zip_images(db: Session, batch: ImportBatch, rel_path: str, source_dir: Path) -> None:
    full_path = absolute_path(rel_path)
    try:
        with zipfile.ZipFile(full_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                suffix = Path(info.filename).suffix.lower()
                if suffix not in IMAGE_EXTENSIONS:
                    continue
                target = source_dir / f"{uuid.uuid4().hex}{suffix}"
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                _register_image_page(db, batch, relative_to_root(target), info.filename)
    except zipfile.BadZipFile:
        logger.warning("无效的 zip 包: %s", rel_path)


# ---------------- 分片上传 / 断点续传 ----------------

DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB


def _chunk_dir(batch: ImportBatch, upload_id: str) -> Path:
    return get_batch_dir(batch.exam_id, batch.id, f"chunks/{upload_id}")


def _chunk_meta(batch: ImportBatch, upload_id: str) -> dict:
    meta_path = _chunk_dir(batch, upload_id) / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分片上传会话不存在或已过期")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _validate_filename(batch: ImportBatch, filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    if batch.import_type == "pdf":
        if suffix != ".pdf":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PDF 模式仅支持 .pdf 文件")
    elif suffix not in IMAGE_EXTENSIONS and suffix != ".zip":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="图片模式仅支持 jpg/png/bmp/tif/webp 及 .zip 图片包",
        )


def init_chunk_upload(
    db: Session, batch: ImportBatch, filename: str, total_size: int, chunk_size: Optional[int] = None
) -> dict:
    """创建分片上传会话，返回分片参数与已接收分片列表（用于断点续传）。"""
    check_batch_exam_modifiable(db, batch)
    _validate_filename(batch, filename)
    size = int(chunk_size) if chunk_size else DEFAULT_CHUNK_SIZE
    size = max(256 * 1024, min(size, 32 * 1024 * 1024))

    upload_id = uuid.uuid4().hex
    total_chunks = max(1, math.ceil(total_size / size))
    chunk_dir = _chunk_dir(batch, upload_id)
    ensure_dir(chunk_dir)
    meta = {
        "filename": filename,
        "total_size": int(total_size),
        "chunk_size": size,
        "total_chunks": total_chunks,
    }
    (chunk_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"upload_id": upload_id, **meta, "received": [], "completed": False}


def chunk_upload_status(batch: ImportBatch, upload_id: str) -> dict:
    meta = _chunk_meta(batch, upload_id)
    chunk_dir = _chunk_dir(batch, upload_id)
    received = sorted(
        int(p.name.split("_")[1]) for p in chunk_dir.glob("part_*") if p.name.split("_")[1].isdigit()
    )
    return {
        "upload_id": upload_id,
        **meta,
        "received": received,
        "completed": len(received) == meta["total_chunks"],
    }


def save_chunk(batch: ImportBatch, upload_id: str, index: int, data: bytes) -> dict:
    """写入单个分片（幂等，重复上传同序号分片会覆盖），返回最新状态。"""
    meta = _chunk_meta(batch, upload_id)
    if index < 0 or index >= meta["total_chunks"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分片序号越界")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分片内容为空")

    target = _chunk_dir(batch, upload_id) / f"part_{index:05d}"
    target.write_bytes(data)
    return chunk_upload_status(batch, upload_id)


def complete_chunk_upload(db: Session, batch: ImportBatch, upload_id: str) -> dict:
    """校验分片完整性，合并落盘并登记答卷页。"""
    check_batch_exam_modifiable(db, batch)
    state = chunk_upload_status(batch, upload_id)
    if not state["completed"]:
        missing = state["total_chunks"] - len(state["received"])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"分片不完整，仍缺少 {missing} 个分片",
        )

    chunk_dir = _chunk_dir(batch, upload_id)
    source_sub = "source_pdfs" if batch.import_type == "pdf" else "source_images"
    source_dir = get_batch_dir(batch.exam_id, batch.id, source_sub)
    suffix = Path(state["filename"]).suffix.lower()
    target = source_dir / f"{uuid.uuid4().hex}{suffix}"

    existing_ids = {p.id for p in db.query(ImportedPage.id).filter(ImportedPage.batch_id == batch.id).all()}

    with open(target, "wb") as out:
        for i in range(state["total_chunks"]):
            out.write((chunk_dir / f"part_{i:05d}").read_bytes())

    shutil.rmtree(chunk_dir, ignore_errors=True)

    rel_path = relative_to_root(target)
    if not _accept_saved_file(db, batch, rel_path, state["filename"]):
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件类型不受支持")

    batch.total_files += 1
    db.flush()
    batch.total_pages = db.query(ImportedPage).filter(ImportedPage.batch_id == batch.id).count()
    db.commit()
    db.refresh(batch)

    pages = [
        p for p in db.query(ImportedPage).filter(ImportedPage.batch_id == batch.id).all()
        if p.id not in existing_ids
    ]
    return {"batch": batch, "pages": pages}


# ---------------- 处理流水线 ----------------

def process_batch(batch_id: str | UUID) -> None:
    """执行导入批次全量处理。使用独立会话，可被 Celery 或后台任务调用。"""
    db = SessionLocal()
    try:
        batch = db.query(ImportBatch).filter(ImportBatch.id == _as_uuid(batch_id)).first()
        if not batch:
            logger.error("批次不存在: %s", batch_id)
            return
        if batch.status == "processing":
            logger.info("批次 %s 正在处理中，跳过", batch_id)
            return

        batch.status = "processing"
        batch.started_at = datetime.now(timezone.utc)
        batch.processed_pages = 0
        batch.message = None
        db.commit()

        exam = db.query(Exam).filter(Exam.id == batch.exam_id).first()
        if not exam or not exam.answer_card_template_id:
            _fail(db, batch, "考试未绑定答题卡模板")
            return

        template = db.query(AnswerCardTemplate).filter(AnswerCardTemplate.id == exam.answer_card_template_id).first()
        if not template:
            _fail(db, batch, "答题卡模板不存在")
            return

        regions = db.query(TemplateRegion).filter(TemplateRegion.template_id == template.id).all()
        page_count = max(1, template.page_count)

        pages = (
            db.query(ImportedPage)
            .filter(ImportedPage.batch_id == batch.id)
            .order_by(ImportedPage.created_at, ImportedPage.original_page_index)
            .all()
        )

        # 按源文件分组：同一文件（一位学生的整份答卷）共享考号识别结果
        groups: dict[str, List[ImportedPage]] = {}
        for p in pages:
            groups.setdefault(p.original_file_path, []).append(p)

        for file_pages in groups.values():
            try:
                _process_file_group(db, batch, template, regions, page_count, file_pages)
            except Exception as exc:  # noqa: BLE001
                logger.exception("处理文件失败: %s", exc)
                batch.message = f"部分文件处理失败: {exc}"
            db.commit()
            _publish_progress(db, batch, exam)

        batch.status = "completed"
        batch.completed_at = datetime.now(timezone.utc)
        batch.total_pages = db.query(ImportedPage).filter(ImportedPage.batch_id == batch.id).count()
        batch.processed_pages = batch.total_pages
        db.commit()

        # 导入完成后自动执行选择题判分（失败不影响导入结果）
        try:
            from app.services import choice_service
            stats = choice_service.grade_exam_choices(db, batch.exam_id)
            logger.info("选择题自动判分完成 exam=%s stats=%s", batch.exam_id, stats)
        except Exception as exc:  # noqa: BLE001
            logger.exception("选择题自动判分失败 exam=%s: %s", batch.exam_id, exc)
            db.rollback()

        _publish_progress(db, batch, exam)
        _emit_import_finished(db, batch, exam)
    except Exception as exc:  # noqa: BLE001
        logger.exception("批次处理失败: %s", exc)
        db.rollback()
        batch = db.query(ImportBatch).filter(ImportBatch.id == _as_uuid(batch_id)).first()
        if batch:
            _fail(db, batch, str(exc))
    finally:
        db.close()


def _process_file_group(
    db: Session,
    batch: ImportBatch,
    template: AnswerCardTemplate,
    regions: List[TemplateRegion],
    page_count: int,
    pages: List[ImportedPage],
) -> None:
    # 1. 逐页渲染 + 预处理
    prepared: List[Tuple[ImportedPage, np.ndarray, dict]] = []
    for page in pages:
        try:
            raw = _load_page_image(page)
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取答卷页失败 page=%s: %s", page.id, exc)
            _add_exception(db, batch, page, None, "cut_failed", "答卷页读取失败")
            page.status = "exception"
            continue

        processed, meta = image_utils.preprocess_page(
            raw,
            deskew=template.deskew_enabled,
            max_tilt=float(template.tilt_threshold or 15),
        )
        try:
            processed_path = get_batch_dir(page.exam_id, batch.id, "preprocessed") / f"{page.id}.png"
            image_utils.save_image(processed, processed_path)
            page.preprocessed_image_path = relative_to_root(processed_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("预处理图像保存失败 page=%s: %s", page.id, exc)

        page.tilt_angle = meta["tilt_angle"]
        page.perspective_corrected = meta["perspective_corrected"]
        if meta["tilt_exceed"]:
            _add_exception(
                db, batch, page, None, "tilt_exceed",
                f"倾斜角度 {meta['tilt_angle']:.1f}° 超限",
                snapshot=page.preprocessed_image_path,
            )
        prepared.append((page, processed, meta))

    if not prepared:
        return

    # 2. 识别考号（取该文件首个含考号区且识别成功的页）
    exam_number, matched_student, page_of_number = _resolve_exam_number(
        db, batch, template, regions, page_count, prepared
    )

    # 3. 回填考号/学生 + 切割题块（题块组可跨页合并）+ 更新页状态
    for page, _processed, _meta in prepared:
        page.exam_number_ocr = exam_number
        page.student_id = matched_student.id if matched_student else None

    _cut_blocks_file_group(db, batch, regions, page_count, prepared)

    for page, _processed, _meta in prepared:
        page.status = "exception" if _page_has_exception(db, page) else (
            "processed" if matched_student else "matched"
        )

    db.flush()


def _resolve_exam_number(
    db: Session,
    batch: ImportBatch,
    template: AnswerCardTemplate,
    regions: List[TemplateRegion],
    page_count: int,
    prepared: List[Tuple[ImportedPage, np.ndarray, dict]],
) -> Tuple[Optional[str], Optional[Student], Optional[ImportedPage]]:
    digits = int(template.exam_number_digits or 9)
    exam_number_region = next((r for r in regions if r.region_type == "exam_number"), None)

    if not exam_number_region:
        return None, None, None

    recognized: Optional[str] = None
    source_page: Optional[ImportedPage] = None
    for page, processed, _meta in prepared:
        page_index = _page_index(page, page_count)
        if exam_number_region.page_index != page_index:
            continue
        crop = image_utils.crop_region(
            processed,
            float(exam_number_region.x), float(exam_number_region.y),
            float(exam_number_region.width), float(exam_number_region.height),
        )
        # 标注式模板：优先使用框选时持久化的考号填涂格坐标（适配真实答题卡）
        spec = choice_grid_service.digit_grid(exam_number_region)
        if spec:
            cols, rows, radius = spec
            value, confidence = omr.read_by_grid(
                crop, digits=digits,
                column_x_fractions=cols, row_y_fractions=rows,
                fill_threshold=settings.OMR_FILL_THRESHOLD,
                bubble_radius_fraction=radius,
            )
        else:
            grid = _exam_number_grid(template, exam_number_region)
            value, confidence = omr.recognize_exam_number(
                crop, digits=digits, fill_threshold=settings.OMR_FILL_THRESHOLD,
                column_x_fractions=grid[0] if grid else None,
                row_y_fractions=grid[1] if grid else None,
                bubble_radius_fraction=grid[2] if grid else 0.01,
            )
        if value:
            recognized = value
            source_page = page
            break

    if not recognized:
        _add_exception(
            db, batch, prepared[0][0], None, "exam_number_not_found",
            "考号识别失败，需人工指定考号",
            snapshot=prepared[0][0].preprocessed_image_path,
        )
        return None, None, None

    student = (
        db.query(Student)
        .join(ExamStudent, ExamStudent.student_id == Student.id)
        .filter(ExamStudent.exam_id == batch.exam_id, Student.exam_number == recognized)
        .first()
    )
    if not student:
        _add_exception(
            db, batch, source_page or prepared[0][0], None, "exam_number_not_match",
            f"识别考号 {recognized} 不在本场考试花名册中",
            snapshot=(source_page or prepared[0][0]).preprocessed_image_path,
        )
        return recognized, None, source_page

    return recognized, student, source_page


def _collect_block_groups(
    regions: List[TemplateRegion],
    page_count: int,
    prepared: List[Tuple[ImportedPage, np.ndarray, dict]],
) -> List[List[Tuple[TemplateRegion, ImportedPage, np.ndarray]]]:
    """把文件组内各页区域聚合为待切割题块。

    同一道非选择题跨页 / 跨栏被框选成多个区域时共享 group_key，合并为一个题块
    （各区域作答图纵向拼接）；姓名 / 考号区仅用于识别与定位，不参与阅卷，不切割。
    """
    singles: List[List[Tuple[TemplateRegion, ImportedPage, np.ndarray]]] = []
    by_group: dict[str, List[Tuple[TemplateRegion, ImportedPage, np.ndarray]]] = {}
    for page, processed, _meta in prepared:
        page_index = _page_index(page, page_count)
        for region in regions:
            if region.page_index != page_index:
                continue
            if region.region_type not in ("choice", "subjective"):
                continue
            entry = (region, page, processed)
            key = region.group_key if region.region_type == "subjective" else None
            if key:
                by_group.setdefault(key, []).append(entry)
            else:
                singles.append([entry])
    return singles + list(by_group.values())


def _cut_blocks_file_group(
    db: Session,
    batch: ImportBatch,
    regions: List[TemplateRegion],
    page_count: int,
    prepared: List[Tuple[ImportedPage, np.ndarray, dict]],
) -> None:
    """按文件组切割全部题块（题块组可跨页合并）。"""
    if not prepared:
        return
    blocks_dir = get_batch_dir(batch.exam_id, batch.id, "blocks")
    for group in _collect_block_groups(regions, page_count, prepared):
        _cut_block(db, batch, group, blocks_dir)


def _cut_block(
    db: Session,
    batch: ImportBatch,
    group: List[Tuple[TemplateRegion, ImportedPage, np.ndarray]],
    blocks_dir: Path,
) -> None:
    """切割单个题块：单区域直接裁剪，题块组则纵向拼接各区域作答图（可跨页）。"""
    primary, primary_page, _ = group[0]
    x = min(float(r.x) for r, _p, _im in group)
    y = min(float(r.y) for r, _p, _im in group)
    width = max(float(r.x) + float(r.width) for r, _p, _im in group) - x
    height = max(float(r.y) + float(r.height) for r, _p, _im in group) - y

    block = AnswerBlock(
        page_id=primary_page.id,
        exam_id=primary_page.exam_id,
        student_id=primary_page.student_id,
        region_id=primary.id,
        question_number=primary.question_number,
        block_type=primary.region_type,
        x=x, y=y, width=width, height=height,
        status="pending",
    )
    db.add(block)
    db.flush()

    try:
        crops = [
            image_utils.crop_region(im, float(r.x), float(r.y), float(r.width), float(r.height))
            for r, _p, im in group
        ]
        if any(c.size == 0 or min(c.shape[:2]) < 4 for c in crops):
            raise ValueError("切割区域过小")
        crop = crops[0] if len(crops) == 1 else _stack_crops(crops)
        block_path = blocks_dir / f"{block.id}.png"
        image_utils.save_image(crop, block_path)
        block.image_path = relative_to_root(block_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("题块切割失败 block=%s: %s", block.id, exc)
        block.status = "exception"
        _add_exception(
            db, batch, primary_page, block, "cut_failed",
            f"题块 {primary.question_number or primary.region_type} 切割失败",
            snapshot=primary_page.preprocessed_image_path,
        )


def _recut_file_group_blocks(
    db: Session,
    batch: ImportBatch,
    template: AnswerCardTemplate,
    page: ImportedPage,
    processed: np.ndarray,
) -> None:
    """重切该页所在文件组的全部题块（含跨页题块组），保证合并口径一致。"""
    page_count = max(1, template.page_count)
    siblings = (
        db.query(ImportedPage)
        .filter(
            ImportedPage.batch_id == page.batch_id,
            ImportedPage.original_file_path == page.original_file_path,
        )
        .order_by(ImportedPage.original_page_index)
        .all()
    )
    if not siblings:
        return

    regions = db.query(TemplateRegion).filter(TemplateRegion.template_id == template.id).all()
    sibling_ids = [p.id for p in siblings]
    sibling_indexes = {_page_index(p, page_count) for p in siblings}
    sibling_region_ids = [r.id for r in regions if r.page_index in sibling_indexes]

    # 删除本文件组题块：直接归属的，以及题块组区域落在本组页上的
    db.query(AnswerBlock).filter(
        AnswerBlock.exam_id == page.exam_id,
        or_(
            AnswerBlock.page_id.in_(sibling_ids),
            AnswerBlock.region_id.in_(sibling_region_ids),
        ),
    ).delete(synchronize_session=False)
    db.flush()

    prepared: List[Tuple[ImportedPage, np.ndarray, dict]] = []
    for p in siblings:
        if p.id == page.id:
            prepared.append((p, processed, {}))
            continue
        if not p.preprocessed_image_path:
            continue
        try:
            prepared.append((p, image_utils.load_image(absolute_path(p.preprocessed_image_path)), {}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("重切读取兄弟页图像失败 page=%s: %s", p.id, exc)

    _cut_blocks_file_group(db, batch, regions, page_count, prepared)


def _stack_crops(crops: List[np.ndarray]) -> np.ndarray:
    """将同一题块组的多个区域裁剪图纵向拼接，宽度不足处补白，便于整体阅卷。"""
    width = max(c.shape[1] for c in crops)
    parts: List[np.ndarray] = []
    for c in crops:
        if c.shape[1] < width:
            pad = np.full((c.shape[0], width - c.shape[1], 3), 255, dtype=c.dtype)
            c = np.hstack([c, pad])
        parts.append(c)
    separator = np.full((8, width, 3), 200, dtype=parts[0].dtype)
    stacked = parts[0]
    for part in parts[1:]:
        stacked = np.vstack([stacked, separator, part])
    return stacked


# ---------------- 手动处理 ----------------

def set_page_exam_number(
    db: Session, page_id: UUID, exam_number: str, user_id: UUID
) -> ImportedPage:
    page = db.query(ImportedPage).filter(ImportedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="答卷页不存在")

    batch = db.query(ImportBatch).filter(ImportBatch.id == page.batch_id).first()
    exam = db.query(Exam).filter(Exam.id == page.exam_id).first()
    template = (
        db.query(AnswerCardTemplate).filter(AnswerCardTemplate.id == exam.answer_card_template_id).first()
        if exam and exam.answer_card_template_id else None
    )

    student = (
        db.query(Student)
        .join(ExamStudent, ExamStudent.student_id == Student.id)
        .filter(ExamStudent.exam_id == page.exam_id, Student.exam_number == exam_number)
        .first()
    )

    # 同一文件的其它页同步考号
    siblings = db.query(ImportedPage).filter(
        ImportedPage.batch_id == page.batch_id,
        ImportedPage.original_file_path == page.original_file_path,
    ).all()
    for p in siblings:
        p.exam_number_ocr = exam_number
        p.student_id = student.id if student else None

    # 关闭考号相关异常
    _resolve_page_exceptions(db, page, user_id, "manual_exam_number", f"人工指定考号 {exam_number}")

    if not student:
        _add_exception(
            db, batch, page, None, "exam_number_not_match",
            f"人工指定考号 {exam_number} 不在花名册中",
            snapshot=page.preprocessed_image_path,
        )
        page.status = "exception"
        db.commit()
        db.refresh(page)
        return page

    # 学生已匹配：补齐题块（重切整个文件组，含跨页题块组）
    if template and page.preprocessed_image_path and not db.query(AnswerBlock).filter(
        AnswerBlock.page_id == page.id
    ).first():
        processed = image_utils.load_image(absolute_path(page.preprocessed_image_path))
        _recut_file_group_blocks(db, batch, template, page, processed)

    for p in siblings:
        p.status = "processed"

    db.commit()
    db.refresh(page)
    return page


def recut_page(
    db: Session,
    page_id: UUID,
    user_id: UUID,
    perspective_points: Optional[List[List[float]]] = None,
) -> ImportedPage:
    """对单页重新预处理与切割，支持传入四点透视矫正坐标。"""
    page = db.query(ImportedPage).filter(ImportedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="答卷页不存在")

    batch = db.query(ImportBatch).filter(ImportBatch.id == page.batch_id).first()
    exam = db.query(Exam).filter(Exam.id == page.exam_id).first()
    template = (
        db.query(AnswerCardTemplate).filter(AnswerCardTemplate.id == exam.answer_card_template_id).first()
        if exam and exam.answer_card_template_id else None
    )
    if not template:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="考试未绑定答题卡模板")

    raw = _load_page_image(page)
    processed, meta = image_utils.preprocess_page(
        raw,
        deskew=template.deskew_enabled,
        max_tilt=float(template.tilt_threshold or 15),
        perspective_points=perspective_points,
    )
    processed_path = get_batch_dir(page.exam_id, page.batch_id, "preprocessed") / f"{page.id}.png"
    image_utils.save_image(processed, processed_path)
    page.preprocessed_image_path = relative_to_root(processed_path)
    page.tilt_angle = meta["tilt_angle"]
    page.perspective_corrected = meta["perspective_corrected"]

    # 清理该页的 cut_failed / tilt_exceed 异常
    db.query(ExamException).filter(
        ExamException.page_id == page.id,
        ExamException.exception_type.in_(["cut_failed", "tilt_exceed"]),
        ExamException.status == "pending",
    ).update({
        ExamException.status: "resolved",
        ExamException.resolved_by: user_id,
        ExamException.resolved_at: datetime.now(timezone.utc),
        ExamException.resolution_action: "recut",
    }, synchronize_session=False)

    # 重建题块：重切整个文件组，跨页题块组保持一致
    _recut_file_group_blocks(db, batch, template, page, processed)
    if meta["tilt_exceed"]:
        _add_exception(
            db, batch, page, None, "tilt_exceed",
            f"倾斜角度 {meta['tilt_angle']:.1f}° 超限",
            snapshot=page.preprocessed_image_path,
        )
    page.status = "exception" if _page_has_exception(db, page) else (
        "processed" if page.student_id else "matched"
    )
    db.commit()
    db.refresh(page)
    return page


# ---------------- 异常辅助 ----------------

def _add_exception(
    db: Session,
    batch: ImportBatch,
    page: Optional[ImportedPage],
    block: Optional[AnswerBlock],
    exception_type: str,
    description: str,
    snapshot: Optional[str] = None,
) -> ExamException:
    # 避免同页同类型重复
    existing = db.query(ExamException).filter(
        ExamException.page_id == (page.id if page else None),
        ExamException.exception_type == exception_type,
        ExamException.status == "pending",
    ).first()
    if existing:
        return existing

    exc = ExamException(
        exam_id=batch.exam_id,
        page_id=page.id if page else None,
        block_id=block.id if block else None,
        exception_type=exception_type,
        source=page.source_type if page else "pdf",
        status="pending",
        description=description,
        snapshot_path=snapshot,
    )
    db.add(exc)
    db.flush()
    return exc


def _page_has_exception(db: Session, page: ImportedPage) -> bool:
    return db.query(ExamException).filter(
        ExamException.page_id == page.id,
        ExamException.status == "pending",
    ).first() is not None


def _resolve_page_exceptions(db: Session, page: ImportedPage, user_id: UUID, action: str, note: str) -> None:
    db.query(ExamException).filter(
        ExamException.page_id == page.id,
        ExamException.exception_type.in_(["exam_number_not_found", "exam_number_not_match"]),
        ExamException.status == "pending",
    ).update({
        ExamException.status: "resolved",
        ExamException.resolved_by: user_id,
        ExamException.resolved_at: datetime.now(timezone.utc),
        ExamException.resolution_action: action,
        ExamException.resolution_note: note,
    }, synchronize_session=False)


# ---------------- 基础辅助 ----------------

def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _exam_number_grid(template: AnswerCardTemplate, region: TemplateRegion):
    """还原考号区填涂块网格在区域内的相对位置（0~1）。

    与 template_service._draw_exam_number_grid 使用同一套布局常量，
    保证按模板打印的答题卡能够被精确采样。返回 (列x比例, 行y比例, 采样半径比例)。
    """
    page_w, page_h = PAPER_SIZES.get(template.paper_size, PAPER_SIZES["A4"])
    region_w_pt = float(region.width) / 1000.0 * page_w
    region_h_pt = float(region.height) / 1000.0 * page_h
    digits = int(template.exam_number_digits or 9)
    if region_w_pt <= 20 or region_h_pt <= 0 or digits < 1:
        return None

    col_width = min(
        EXAM_NUMBER_GRID["col_width"],
        (region_w_pt - 20.0) / digits,
    )
    if col_width <= 0:
        return None

    col_fx = [
        (EXAM_NUMBER_GRID["start_x"] + c * col_width) / region_w_pt
        for c in range(digits)
    ]
    row_fy = [
        (EXAM_NUMBER_GRID["start_y"] + d * EXAM_NUMBER_GRID["row_step"]) / region_h_pt
        for d in range(10)
    ]
    # 仅采样填涂块核心（约半个半径），避开未填涂时的圆圈描边
    core_radius_fraction = (EXAM_NUMBER_GRID["bubble_radius"] * 0.5) / region_h_pt
    return col_fx, row_fy, core_radius_fraction


def _page_index(page: ImportedPage, page_count: int) -> int:
    return (page.original_page_index or 0) % page_count


def _load_page_image(page: ImportedPage) -> np.ndarray:
    full_path = absolute_path(page.original_file_path)
    if page.source_type == "pdf" and full_path.suffix.lower() == ".pdf":
        return _render_pdf_page(full_path, page.original_page_index or 0)
    return image_utils.load_image(full_path)


def load_page_source_image(page: ImportedPage) -> np.ndarray:
    """读取/渲染答卷原文件为图像（PDF 自动转图），供前端交互使用。"""
    return _load_page_image(page)


def _render_pdf_page(path: Path, page_index: int) -> np.ndarray:
    doc = fitz.open(path)
    try:
        index = min(max(0, page_index), doc.page_count - 1)
        pdf_page = doc.load_page(index)
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(PDF_ZOOM, PDF_ZOOM))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = img[:, :, :3]
        return img[:, :, ::-1].copy()  # RGB -> BGR
    finally:
        doc.close()


def get_progress(db: Session, batch: ImportBatch) -> dict:
    total = db.query(ImportedPage).filter(ImportedPage.batch_id == batch.id).count()
    processed = db.query(ImportedPage).filter(
        ImportedPage.batch_id == batch.id,
        ImportedPage.status.in_(["processed", "matched", "exception"]),
    ).count()
    pending_exceptions = db.query(ExamException).filter(
        ExamException.exam_id == batch.exam_id,
        ExamException.status == "pending",
    ).count()
    percent = round(processed / total * 100, 1) if total else 0.0
    if batch.status == "completed":
        percent = 100.0
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "total_pages": total,
        "processed_pages": processed,
        "percent": percent,
        "exception_count": pending_exceptions,
        "message": batch.message,
    }


def _publish_progress(db: Session, batch: ImportBatch, exam: Exam) -> None:
    """实时推送批次导入进度（订阅 exam:<id> 与 exams 的客户端可即时刷新）。"""
    realtime.publish_exam_event(exam.id, "import_progress", get_progress(db, batch))


def _emit_import_finished(db: Session, batch: ImportBatch, exam: Exam) -> None:
    """导入完成后投递站内通知（是否投递由系统通知配置决定）。"""
    notification_service.emit_event(
        "import_finished",
        content=f"考试「{exam.name}」答卷导入完成，共处理 {batch.processed_pages} 页",
        link=f"/imports?exam_id={exam.id}",
        recipient_roles=["exam_admin", "group_leader"],
        meta={"exam_id": str(exam.id), "batch_id": str(batch.id)},
        db=db,
    )


def delete_batch_files(batch: ImportBatch) -> None:
    batch_dir = Path(settings.STORAGE_ROOT) / "exams" / str(batch.exam_id) / "imports" / str(batch.id)
    if batch_dir.exists():
        shutil.rmtree(batch_dir, ignore_errors=True)