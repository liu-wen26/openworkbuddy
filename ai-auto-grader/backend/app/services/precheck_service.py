"""预阅卷预览服务（F5 系列）。

在正式导入前，用少量样卷复用「预处理 → 考号识别 → 题块切割 → 选择题 OMR →
非选择题 AI 预评」整条链路做试跑，结果只写入 precheck_sessions / precheck_pages
快照，便于迭代调试模板与 AI 配置，测试完成后可一键清空。

关键约束：不与正式数据混用 —— 不写 answer_blocks / choice_results /
subjective_results / exam_exceptions。
"""

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
import pymupdf as fitz
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import SessionLocal
from app.models.exam import Exam
from app.models.precheck import PrecheckPage, PrecheckSession
from app.models.student import ExamStudent, Student
from app.models.template import AnswerCardTemplate
from app.models.template_config import AIScoringConfig, ChoiceAnswer, TemplateRegion
from app.services import ai_service, choice_grid_service, ocr_service
from app.services.choice_service import _choice_grid
from app.services.exam_service import check_exam_modifiable
from app.services.import_service import _exam_number_grid, _render_pdf_page, _stack_crops
from app.utils import image as image_utils
from app.utils import omr
from app.utils.file_storage import absolute_path, ensure_dir, relative_to_root, save_upload_to

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_SAMPLES = 20
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
# 会话生命周期：active（可上传/可运行）-> running（执行中）-> done（已运行，可再上传/重跑）；cleared（已清空）
REUSABLE_STATUSES = ("active", "running", "done")
RUNNABLE_STATUSES = ("active", "done")


# ---------------- 会话管理 ----------------

def get_exam_or_404(db: Session, exam_id: UUID) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


def get_session_or_404(db: Session, session_id: UUID) -> PrecheckSession:
    session = db.query(PrecheckSession).filter(PrecheckSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预阅卷会话不存在")
    return session


def open_session(db: Session, exam_id: UUID, user_id: UUID) -> PrecheckSession:
    """打开（或复用）该考试的活跃预阅卷会话。"""
    exam = get_exam_or_404(db, exam_id)
    check_exam_modifiable(exam)
    if not exam.answer_card_template_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该考试尚未绑定答题卡模板")

    existing = (
        db.query(PrecheckSession)
        .filter(PrecheckSession.exam_id == exam_id, PrecheckSession.status.in_(REUSABLE_STATUSES))
        .order_by(PrecheckSession.created_at.desc())
        .first()
    )
    if existing:
        return existing

    session = PrecheckSession(exam_id=exam_id, status="active", created_by=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, exam_id: UUID) -> List[PrecheckSession]:
    return (
        db.query(PrecheckSession)
        .filter(PrecheckSession.exam_id == exam_id)
        .order_by(PrecheckSession.created_at.desc())
        .all()
    )


# ---------------- 样卷上传 ----------------

def save_samples(db: Session, session: PrecheckSession, files: List[UploadFile]) -> Tuple[int, List[PrecheckPage]]:
    """保存样卷文件（最多 20 份），登记样卷页，返回 (新增份数, 新增页)。"""
    check_exam_modifiable(get_exam_or_404(db, session.exam_id))
    if session.status not in RUNNABLE_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该会话正在执行或已清空，请稍后再试")
    # 已运行过的会话再次上传样卷时回到可编辑状态
    if session.status == "done":
        session.status = "active"

    source_dir = _precheck_dir(session, "source")
    template = _get_template(db, session.exam_id)
    page_count = max(1, template.page_count) if template else 1

    added = 0
    new_pages: List[PrecheckPage] = []
    for file in files:
        if session.sample_count >= MAX_SAMPLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"样卷数量已达上限（{MAX_SAMPLES} 份）",
            )
        filename = file.filename or "sample"
        suffix = Path(filename).suffix.lower()
        is_pdf = suffix == ".pdf"
        if not is_pdf and suffix not in IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="样卷仅支持 PDF 或 jpg/png/bmp/tif/webp 图片",
            )

        stored_name = f"{uuid.uuid4().hex}{suffix}"
        rel_path = save_upload_to(file, source_dir, stored_name)

        pages = _register_pages(db, session, rel_path, is_pdf, page_count)
        session.sample_count += 1
        added += 1
        new_pages.extend(pages)

    db.flush()
    session.page_count = db.query(PrecheckPage).filter(PrecheckPage.session_id == session.id).count()
    session.message = None
    db.commit()
    db.refresh(session)
    return added, new_pages


def _register_pages(
    db: Session, session: PrecheckSession, rel_path: str, is_pdf: bool, page_count: int
) -> List[PrecheckPage]:
    if is_pdf:
        try:
            doc = fitz.open(absolute_path(rel_path))
            pages = doc.page_count
            doc.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("无法解析样卷 PDF %s: %s", rel_path, exc)
            pages = 1
        indices = list(range(max(1, pages)))
        source_type = "pdf"
    else:
        indices = [0]
        source_type = "image"

    created: List[PrecheckPage] = []
    for index in indices:
        page = PrecheckPage(
            session_id=session.id,
            source_type=source_type,
            original_file_path=rel_path,
            original_page_index=index,
            status="pending",
        )
        db.add(page)
        created.append(page)
    db.flush()
    return created


# ---------------- 预阅卷流水线 ----------------

def run_precheck(session_id: str | UUID) -> None:
    """执行预阅卷全量处理。使用独立会话，可被 Celery 或后台任务调用。"""
    db = SessionLocal()
    try:
        session = db.query(PrecheckSession).filter(PrecheckSession.id == _as_uuid(session_id)).first()
        if not session:
            logger.error("预阅卷会话不存在: %s", session_id)
            return
        if session.status not in RUNNABLE_STATUSES:
            logger.info("预阅卷会话 %s 当前状态 %s，跳过", session_id, session.status)
            return

        # 标记执行中，前端据此展示「运行中」
        session.status = "running"
        session.message = None
        db.commit()

        exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
        template = _get_template(db, session.exam_id)
        if not exam or not template:
            session.message = "考试未绑定答题卡模板"
            session.status = "active"
            db.commit()
            return

        regions = db.query(TemplateRegion).filter(TemplateRegion.template_id == template.id).all()
        page_count = max(1, template.page_count)
        choice_answers = _choice_answer_map(db, exam.id, template.id)
        ai_configs = _ai_config_map(db, exam)
        provider = ai_service.get_ai_provider()

        pages = (
            db.query(PrecheckPage)
            .filter(PrecheckPage.session_id == session.id)
            .order_by(PrecheckPage.created_at, PrecheckPage.original_page_index)
            .all()
        )

        summary = _empty_summary()
        summary["samples"] = session.sample_count
        summary["provider"] = provider.name
        roster_numbers = _exam_number_set(db, exam.id)

        # 1) 逐页预处理 + 考号识别（跨页题块组需先拿到文件组内全部页的预处理图）
        prepared_by_file: Dict[str, List[Tuple[PrecheckPage, np.ndarray]]] = {}
        for page in pages:
            try:
                processed = _preprocess_page(session, template, page)
                page_regions = [r for r in regions if r.page_index == _page_index(page, page_count)]
                identity = _recognize_identity(processed, template, page_regions)
                page.exam_number_ocr = identity.get("exam_number")
                page.name_ocr = identity.get("name")
                page.class_ocr = identity.get("class_name")
                prepared_by_file.setdefault(page.original_file_path, []).append((page, processed))
            except Exception as exc:  # noqa: BLE001
                logger.exception("预阅卷预处理页失败 page=%s: %s", page.id, exc)
                page.status = "exception"
                page.cut_result = page.cut_result or []
                db.flush()

        # 2) 按源文件分组切割 + OMR / AI（题块组口径与正式导入一致，支持跨页合并）
        for file_pages in prepared_by_file.values():
            try:
                _process_group_pages(
                    db, session, template, regions, page_count, file_pages,
                    choice_answers, ai_configs, provider,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("预阅卷切割失败 file=%s: %s", file_pages[0][0].original_file_path, exc)
                for p, _img in file_pages:
                    p.status = "exception"
                db.flush()

        for page in pages:
            if page.status != "pending":
                summary["pages"] += 1
            _accumulate(summary, page, roster_numbers)

        session.page_count = len(pages)
        session.summary = summary
        session.status = "done"
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("预阅卷处理失败: %s", exc)
        db.rollback()
        session = db.query(PrecheckSession).filter(PrecheckSession.id == _as_uuid(session_id)).first()
        if session:
            session.message = f"预阅卷处理失败: {exc}"
            session.status = "done"
            db.commit()
    finally:
        db.close()


def _preprocess_page(session: PrecheckSession, template: AnswerCardTemplate, page: PrecheckPage) -> np.ndarray:
    """渲染 + 预处理单页，落盘并回填倾斜角，返回预处理图。"""
    raw = _load_page_image(page)
    processed, meta = image_utils.preprocess_page(
        raw,
        deskew=template.deskew_enabled,
        max_tilt=float(template.tilt_threshold or 15),
    )
    processed_dir = _precheck_dir(session, "preprocessed")
    processed_path = processed_dir / f"{page.id}.png"
    image_utils.save_image(processed, processed_path)
    page.preprocessed_image_path = relative_to_root(processed_path)
    page.tilt_angle = meta["tilt_angle"]
    return processed


def _process_group_pages(
    db: Session,
    session: PrecheckSession,
    template: AnswerCardTemplate,
    regions: List[TemplateRegion],
    page_count: int,
    file_pages: List[Tuple[PrecheckPage, np.ndarray]],
    choice_answers: Dict[str, ChoiceAnswer],
    ai_configs: Dict[str, AIScoringConfig],
    provider: ai_service.AIServiceProvider,
) -> None:
    """处理同一源文件（一位学生整份答卷）的样卷页：切割 + OMR + AI。

    题块组（group_key）可跨页合并，切割结果归属到主区域所在页，与正式导入一致。
    """
    cut_by_page: Dict[UUID, List[dict]] = {p.id: [] for p, _ in file_pages}
    omr_by_page: Dict[UUID, List[dict]] = {p.id: [] for p, _ in file_pages}
    ai_by_page: Dict[UUID, List[dict]] = {p.id: [] for p, _ in file_pages}
    failure_by_page: Dict[UUID, bool] = {p.id: False for p, _ in file_pages}

    blocks_dir = _precheck_dir(session, "blocks")
    for order, group in enumerate(_collect_precheck_groups(regions, page_count, file_pages)):
        region = group[0][0]
        primary_page = group[0][1]
        block, crop = _cut_group(group, blocks_dir, order)
        if block["status"] != "ok":
            failure_by_page[primary_page.id] = True
            block.pop("_crop", None)
            cut_by_page[primary_page.id].append(block)
            continue

        if region.region_type == "choice":
            omr_by_page[primary_page.id].append(_run_omr(crop, block, region, choice_answers, template))
        elif region.region_type == "subjective":
            ai_by_page[primary_page.id].append(_run_ai(crop, block, region, ai_configs, provider))
        block.pop("_crop", None)
        cut_by_page[primary_page.id].append(block)

    for page, _img in file_pages:
        page.cut_result = cut_by_page[page.id]
        page.omr_result = omr_by_page[page.id]
        page.ai_result = ai_by_page[page.id]
        page.status = "exception" if failure_by_page[page.id] else "processed"
    db.flush()


def _collect_precheck_groups(
    regions: List[TemplateRegion],
    page_count: int,
    file_pages: List[Tuple[PrecheckPage, np.ndarray]],
) -> List[List[Tuple[TemplateRegion, PrecheckPage, np.ndarray]]]:
    """把文件组内各页区域聚合为待切割题块，共享 group_key 的非选择题跨页合并。

    与正式导入的切割口径保持一致；姓名 / 考号区仍保留展示，便于核对框选。
    """
    singles: List[List[Tuple[TemplateRegion, PrecheckPage, np.ndarray]]] = []
    by_group: Dict[str, List[Tuple[TemplateRegion, PrecheckPage, np.ndarray]]] = {}
    for page, processed in file_pages:
        page_index = _page_index(page, page_count)
        for region in regions:
            if region.page_index != page_index:
                continue
            entry = (region, page, processed)
            key = region.group_key if region.region_type == "subjective" else None
            if key:
                by_group.setdefault(key, []).append(entry)
            else:
                singles.append([entry])
    return singles + list(by_group.values())


def _cut_group(
    group: List[Tuple[TemplateRegion, PrecheckPage, np.ndarray]], blocks_dir: Path, order: int
) -> Tuple[dict, Optional[np.ndarray]]:
    """切割单个题块：题块组则纵向拼接各区域作答图（可跨页）。"""
    primary, primary_page, _ = group[0]
    # 注：考号 / 姓名区只用于识别与定位，不入阅卷范围，这里仍然展示出来便于核对框选
    max_score = (
        sum(float(r.max_score or 0) for r, _p, _im in group)
        if primary.region_type == "subjective" else float(primary.max_score or 0)
    )
    left = min(float(r.x) for r, _p, _im in group)
    top = min(float(r.y) for r, _p, _im in group)
    right = max(float(r.x) + float(r.width) for r, _p, _im in group)
    bottom = max(float(r.y) + float(r.height) for r, _p, _im in group)
    block = {
        "index": order,
        "region_type": primary.region_type,
        "question_number": primary.question_number,
        "sub_question_number": primary.sub_question_number,
        "group_key": primary.group_key,
        "region_count": len(group),
        "page_id": str(primary_page.id),
        "max_score": max_score,
        "options_count": int(primary.options_count or 4),
        "allow_multiple": bool(primary.allow_multiple),
        "x": left, "y": top,
        "width": right - left, "height": bottom - top,
        "image_path": None,
        "width_px": 0, "height_px": 0,
        "grading": primary.region_type in ("choice", "subjective"),
        "status": "ok",
        "message": None,
    }
    crop: Optional[np.ndarray] = None
    try:
        crops = [
            image_utils.crop_region(im, float(r.x), float(r.y), float(r.width), float(r.height))
            for r, _p, im in group
        ]
        if any(c.size == 0 or min(c.shape[:2]) < 4 for c in crops):
            raise ValueError("切割区域过小")
        crop = crops[0] if len(crops) == 1 else _stack_crops(crops)
        target_dir = ensure_dir(blocks_dir / str(primary_page.id))
        path = target_dir / f"{order}.png"
        image_utils.save_image(crop, path)
        block["image_path"] = relative_to_root(path)
        block["height_px"], block["width_px"] = int(crop.shape[0]), int(crop.shape[1])
    except Exception as exc:  # noqa: BLE001
        block["status"] = "failed"
        block["message"] = str(exc)
        crop = None
    return block, crop


def _run_omr(
    crop: Optional[np.ndarray],
    block: dict,
    region: TemplateRegion,
    choice_answers: Dict[str, ChoiceAnswer],
    template: AnswerCardTemplate,
) -> dict:
    options_count = int(region.options_count or 4)
    allow_multiple = bool(region.allow_multiple)
    answer = choice_answers.get(region.question_number or "")
    correct_options = (answer.correct_options if answer else "") or ""
    max_score = float(region.max_score or 0) or float(answer.score if answer and answer.score else 0)

    if crop is None:
        rec = {"options": "", "ratios": [0.0] * options_count, "confidence": 0.0, "status": "unreadable"}
    else:
        # 标注式模板：优先使用框选时持久化的气泡坐标（可适配任意真实答题卡）
        spec = choice_grid_service.bubble_centers(region)
        if spec:
            centers, radius = spec
            rec = omr.recognize_choice_by_bubbles(
                crop,
                bubble_centers=centers,
                fill_threshold=settings.OMR_FILL_THRESHOLD,
                bubble_radius_fraction=radius,
            )
        else:
            grid = _choice_grid(template, region)
            rec = omr.recognize_choice(
                crop,
                options_count=options_count,
                fill_threshold=settings.OMR_FILL_THRESHOLD,
                option_x_fraction=grid[0] if grid else None,
                option_y_fractions=grid[1] if grid else None,
                bubble_radius_fraction=grid[2] if grid else 0.02,
            )

    item_status = rec["status"]
    is_correct = False
    score = 0.0
    if not correct_options:
        item_status = "no_answer_key"
    elif rec["status"] == "ok":
        rec_set = set(rec["options"].upper())
        cor_set = set(correct_options.upper())
        is_correct = rec_set == cor_set
        score = max_score if is_correct else 0.0
        if not is_correct and allow_multiple and rec_set and rec_set < cor_set:
            score = round(max_score * 0.5, 2)
    if item_status != "ok":
        score = 0.0

    return {
        "question_number": region.question_number,
        "region_index": block["index"],
        "options_count": options_count,
        "allow_multiple": allow_multiple,
        "recognized_options": rec["options"],
        "correct_options": correct_options,
        "is_correct": is_correct,
        "score": round(float(score), 2),
        "max_score": max_score,
        "confidence": rec["confidence"],
        "fill_ratios": rec["ratios"],
        "status": item_status,
    }


def _run_ai(
    crop: Optional[np.ndarray],
    block: dict,
    region: TemplateRegion,
    ai_configs: Dict[str, AIScoringConfig],
    provider: ai_service.AIServiceProvider,
) -> dict:
    config = ai_configs.get(region.question_number or "")
    # 题块组（group_key）的满分 = 组内各区域分值之和，与正式阅卷一题一任务口径一致
    max_score = float(block.get("max_score") or 0)
    threshold = float(config.confidence_threshold) if config and config.confidence_threshold is not None \
        else float(settings.LLM_CONFIDENCE_THRESHOLD)

    result = {
        "question_number": region.question_number,
        "region_index": block["index"],
        "max_score": max_score,
        "ai_score": None,
        "ai_comment": None,
        "ai_confidence": None,
        "ai_model": None,
        "ai_provider": None,
        "threshold": threshold,
        "low_confidence": False,
        "status": "ok",
    }
    if crop is None:
        result["status"] = "failed"
        result["ai_comment"] = "题块图像不可用"
        return result

    context = {
        "question_number": region.question_number,
        "max_score": max_score,
        "standard_answer": config.standard_answer if config else None,
        "scoring_points": config.scoring_points if config else None,
        "deduction_notes": config.deduction_notes if config else None,
        "prompt_template": config.prompt_template if config else None,
    }
    try:
        ai_out = provider.score_subjective(image_utils.encode_png(crop), context)
    except Exception as exc:  # noqa: BLE001
        logger.warning("预阅卷 AI 评分失败 q=%s: %s", region.question_number, exc)
        result["status"] = "failed"
        result["ai_comment"] = f"AI 评分失败: {exc}"
        return result

    result["ai_score"] = ai_out.score
    result["ai_comment"] = ai_out.comment
    result["ai_confidence"] = ai_out.confidence
    result["ai_model"] = ai_out.model
    result["ai_provider"] = ai_out.provider
    result["low_confidence"] = ai_out.confidence < threshold
    return result


# ---------------- 结果汇总 ----------------

def build_detail(db: Session, session: PrecheckSession) -> dict:
    pages = (
        db.query(PrecheckPage)
        .filter(PrecheckPage.session_id == session.id)
        .order_by(PrecheckPage.created_at, PrecheckPage.original_page_index)
        .all()
    )
    return {
        "session": session,
        "pages": pages,
        "summary": session.summary or _empty_summary(),
    }


def clear_session(db: Session, session: PrecheckSession) -> dict:
    """清空预阅卷数据：删除样卷页记录与全部临时文件。"""
    cleared_pages = db.query(PrecheckPage).filter(PrecheckPage.session_id == session.id).count()
    db.query(PrecheckPage).filter(PrecheckPage.session_id == session.id).delete(synchronize_session=False)
    cleared_samples = session.sample_count
    session.sample_count = 0
    session.page_count = 0
    session.summary = None
    session.message = None
    session.status = "cleared"
    session.cleared_at = datetime.now(timezone.utc)
    db.commit()

    session_dir = _session_dir(session)
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)

    return {
        "session_id": session.id,
        "status": session.status,
        "cleared_pages": cleared_pages,
        "cleared_samples": cleared_samples,
    }


def get_page_or_404(db: Session, page_id: UUID) -> PrecheckPage:
    page = db.query(PrecheckPage).filter(PrecheckPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预阅卷样卷页不存在")
    return page


def get_block_image_path(db: Session, page_id: UUID, block_index: int) -> str:
    page = get_page_or_404(db, page_id)
    for block in (page.cut_result or []):
        if block.get("index") == block_index:
            if not block.get("image_path"):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该题块未生成图像")
            return block["image_path"]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题块不存在")


# ---------------- 基础辅助 ----------------

def _empty_summary() -> dict:
    return {
        "pages": 0,
        "samples": 0,
        "provider": None,
        "cut_blocks": 0,
        "cut_failed": 0,
        "cut_positioning": 0,
        "exam_number_found": 0,
        "exam_number_matched": 0,
        "choice_total": 0,
        "choice_scored": 0,
        "choice_correct": 0,
        "choice_exception": 0,
        "subjective_total": 0,
        "ai_scored": 0,
        "ai_low_confidence": 0,
    }


def _exam_number_set(db: Session, exam_id: UUID) -> set:
    """本场考试花名册中的考号集合，用于预阅卷时校验识别结果能否匹配考生。"""
    rows = (
        db.query(Student.exam_number)
        .join(ExamStudent, ExamStudent.student_id == Student.id)
        .filter(ExamStudent.exam_id == exam_id)
        .all()
    )
    return {r[0] for r in rows if r[0]}


def _accumulate(summary: dict, page: PrecheckPage, roster_numbers: set) -> None:
    for block in (page.cut_result or []):
        # 考号 / 姓名区仅用于识别与定位，不计入阅卷题块统计，保持与正式导入口径一致
        if not block.get("grading", True):
            summary["cut_positioning"] += 1
            continue
        summary["cut_blocks"] += 1
        if block.get("status") != "ok":
            summary["cut_failed"] += 1
    if page.exam_number_ocr:
        summary["exam_number_found"] += 1
        if page.exam_number_ocr in roster_numbers:
            summary["exam_number_matched"] += 1
    for item in (page.omr_result or []):
        summary["choice_total"] += 1
        if item.get("status") == "ok":
            summary["choice_scored"] += 1
            if item.get("is_correct"):
                summary["choice_correct"] += 1
        elif item.get("status") == "no_answer_key":
            pass
        else:
            summary["choice_exception"] += 1
    for item in (page.ai_result or []):
        summary["subjective_total"] += 1
        if item.get("ai_score") is not None:
            summary["ai_scored"] += 1
        if item.get("low_confidence"):
            summary["ai_low_confidence"] += 1


def _get_template(db: Session, exam_id: UUID) -> Optional[AnswerCardTemplate]:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam or not exam.answer_card_template_id:
        return None
    return (
        db.query(AnswerCardTemplate)
        .filter(AnswerCardTemplate.id == exam.answer_card_template_id)
        .first()
    )


def _choice_answer_map(db: Session, exam_id: UUID, template_id: UUID) -> Dict[str, ChoiceAnswer]:
    """题号 -> 标准答案，考试级优先于模板级。"""
    rows = db.query(ChoiceAnswer).filter(ChoiceAnswer.template_id == template_id).all()
    answer_map: Dict[str, ChoiceAnswer] = {}
    for r in rows:
        if r.exam_id is None:
            answer_map.setdefault(r.question_number, r)
    for r in rows:
        if r.exam_id == exam_id:
            answer_map[r.question_number] = r
    return answer_map


def _ai_config_map(db: Session, exam: Exam) -> Dict[str, AIScoringConfig]:
    if not exam.answer_card_template_id:
        return {}
    rows = (
        db.query(AIScoringConfig)
        .filter(AIScoringConfig.template_id == exam.answer_card_template_id)
        .all()
    )
    config_map: Dict[str, AIScoringConfig] = {}
    for r in rows:
        if r.exam_id is None:
            config_map.setdefault(r.question_number, r)
    for r in rows:
        if r.exam_id == exam.id:
            config_map[r.question_number] = r
    return config_map


def _recognize_identity(
    processed: np.ndarray, template: AnswerCardTemplate, page_regions: List[TemplateRegion]
) -> Dict[str, str]:
    """识别该页身份信息（考号 / 姓名 / 班级），口径与正式导入一致。

    exam_number_mode=ocr：三者均由视觉模型识别；omr：考号走填涂识别，
    模板开启姓名 OCR 或存在班级区时再补充姓名 / 班级视觉识别。
    """
    mode = str(template.exam_number_mode or "omr").lower()
    digits = int(template.exam_number_digits or 9)
    result: Dict[str, str] = {}

    if mode == "ocr":
        ocr_regions = [r for r in page_regions if r.region_type in ("exam_number", "name", "class")]
        result.update(ocr_service.recognize_fields(
            processed, ocr_regions, ["exam_number", "name", "class_name"],
            digits=digits, hint=f"考号为 {digits} 位数字，姓名与班级为手写中文",
        ))
        return result

    region = next((r for r in page_regions if r.region_type == "exam_number"), None)
    if region:
        value = _read_exam_number_omr(processed, template, region, digits)
        if value:
            result["exam_number"] = value

    name_class_regions = [r for r in page_regions if r.region_type in ("name", "class")]
    if name_class_regions and (
        template.name_ocr_enabled or any(r.region_type == "class" for r in name_class_regions)
    ):
        result.update(ocr_service.recognize_fields(
            processed, name_class_regions, ["name", "class_name"], hint="姓名与班级为手写中文",
        ))
    return result


def _read_exam_number_omr(
    processed: np.ndarray, template: AnswerCardTemplate, region: TemplateRegion, digits: int
) -> Optional[str]:
    crop = image_utils.crop_region(
        processed, float(region.x), float(region.y),
        float(region.width), float(region.height),
    )
    # 标注式模板：优先使用框选时生成的填涂格坐标（适配真实答题卡）
    spec = choice_grid_service.digit_grid(region)
    if spec:
        cols, rows, radius = spec
        value, _confidence = omr.read_by_grid(
            crop,
            digits=digits,
            column_x_fractions=cols,
            row_y_fractions=rows,
            fill_threshold=settings.OMR_FILL_THRESHOLD,
            bubble_radius_fraction=radius,
        )
    else:
        grid = _exam_number_grid(template, region)
        value, _confidence = omr.recognize_exam_number(
            crop,
            digits=digits,
            fill_threshold=settings.OMR_FILL_THRESHOLD,
            column_x_fractions=grid[0] if grid else None,
            row_y_fractions=grid[1] if grid else None,
            bubble_radius_fraction=grid[2] if grid else 0.01,
        )
    return value


def _page_index(page: PrecheckPage, page_count: int) -> int:
    return (page.original_page_index or 0) % max(1, page_count)


def _load_page_image(page: PrecheckPage) -> np.ndarray:
    full_path = absolute_path(page.original_file_path)
    if page.source_type == "pdf" and full_path.suffix.lower() == ".pdf":
        return _render_pdf_page(full_path, page.original_page_index or 0)
    return image_utils.load_image(full_path)


def _session_dir(session: PrecheckSession) -> Path:
    return Path(settings.STORAGE_ROOT) / "exams" / str(session.exam_id) / "precheck" / str(session.id)


def _precheck_dir(session: PrecheckSession, sub: str) -> Path:
    return ensure_dir(_session_dir(session) / sub)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))