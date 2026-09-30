"""非选择题阅卷服务（F7 系列）。

职责：
1. 阅卷任务分发（F7-01）：由非选择题题块生成/维护评分任务，支持三种模式；
2. AI 评分执行引擎（F7-03）：OCR 图像 + 大模型调用 + 置信度计算，低置信度转异常；
3. 人工评分（一评/二评）、双评仲裁（F7-04）；
4. 阅卷痕迹日志（F7-05）与作答标记（F7-06）。

异常与正常评分共用 answer_blocks，结果写入 subjective_results，
所有关键动作写入 grading_logs。
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.answer_block import AnswerBlock
from app.models.exam import Exam
from app.models.exception import ExamException
from app.models.imported_page import ImportedPage
from app.models.student import Student
from app.models.subjective_result import GradingLog, SubjectiveResult
from app.models.template import AnswerCardTemplate
from app.models.template_config import AIScoringConfig, TemplateRegion
from app.services import ai_service, notification_service, realtime
from app.utils.file_storage import absolute_path

logger = logging.getLogger(__name__)
settings = get_settings()

VALID_MODES = ("manual", "ai_assist", "double")
ANSWER_MARK_VALUES = ("none", "excellent", "typical_error", "blank")
DEFAULT_DOUBLE_TOLERANCE = 1.0
AI_EXCEPTION_PREFIX = "ai_"


# ---------------- 任务生成与分发 ----------------

def ensure_results(db: Session, exam_id: UUID) -> List[SubjectiveResult]:
    """按非选择题题块补齐评分任务（幂等）。返回该考试全部非选择题评分结果。"""
    exam = _get_exam_or_404(db, exam_id)
    regions = _region_map(db, exam)
    blocks = (
        db.query(AnswerBlock)
        .filter(AnswerBlock.exam_id == exam_id, AnswerBlock.block_type == "subjective")
        .all()
    )
    existing = {
        r.block_id: r
        for r in db.query(SubjectiveResult).filter(SubjectiveResult.exam_id == exam_id).all()
    }

    for block in blocks:
        if block.id in existing:
            continue
        region = regions.get(block.region_id)
        result = SubjectiveResult(
            exam_id=exam_id,
            student_id=block.student_id,
            page_id=block.page_id,
            block_id=block.id,
            region_id=block.region_id,
            question_number=block.question_number,
            max_score=float(region.max_score or 0) if region else 0,
            grading_mode="manual",
            status="pending",
        )
        db.add(result)
        existing[block.id] = result

    db.commit()
    return (
        db.query(SubjectiveResult)
        .filter(SubjectiveResult.exam_id == exam_id)
        .order_by(SubjectiveResult.question_number, SubjectiveResult.created_at)
        .all()
    )


def distribute(
    db: Session,
    exam_id: UUID,
    mode: str,
    user_id: UUID,
    assign_to: Optional[UUID] = None,
    question_numbers: Optional[List[str]] = None,
) -> dict:
    """分发阅卷任务：设置阅卷模式与（可选）指定阅卷人。"""
    if mode not in VALID_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="阅卷模式仅支持 manual / ai_assist / double")
    results = ensure_results(db, exam_id)

    wanted = set(question_numbers) if question_numbers else None
    touched = 0
    now = datetime.now(timezone.utc)
    for result in results:
        if wanted and result.question_number not in wanted:
            continue
        result.grading_mode = mode
        if assign_to:
            result.assigned_to = assign_to
            result.assigned_at = now
        touched += 1

    _log(db, exam_id, None, None, "distribute", user_id,
         note=f"阅卷模式设为 {mode}" + (f"，题号 {', '.join(sorted(wanted))}" if wanted else ""),
         detail={"mode": mode, "assign_to": str(assign_to) if assign_to else None, "count": touched})
    db.commit()

    # 实时刷新阅卷进度；若指定了阅卷人，则给其推送任务分配通知
    realtime.publish_exam_event(exam_id, "grading_progress", progress(db, exam_id))
    if assign_to and touched:
        notification_service.emit_event(
            "grading_assigned",
            content=f"您有 {touched} 条非选择题阅卷任务待处理",
            link=f"/grading?exam_id={exam_id}",
            recipient_ids=[assign_to],
            meta={"exam_id": str(exam_id), "count": touched, "mode": mode},
            actor_id=user_id,
            db=db,
        )
    return {"mode": mode, "assigned": touched}


# ---------------- AI 预评引擎 ----------------

def run_ai_scoring(db: Session, exam_id: UUID, only_block_ids: Optional[List[UUID]] = None) -> dict:
    """对非选择题执行 AI 预评。已人工评分的任务不会被覆盖。"""
    exam = _get_exam_or_404(db, exam_id)
    results = ensure_results(db, exam_id)
    if only_block_ids:
        wanted = set(only_block_ids)
        results = [r for r in results if r.block_id in wanted]

    config_map = _ai_config_map(db, exam)
    provider = ai_service.get_ai_provider()
    source_cache: Dict[UUID, str] = {}
    stats = {"scored": 0, "low_confidence": 0, "skipped": 0, "failed": 0, "provider": provider.name}

    for result in results:
        if result.first_score is not None or result.status in ("arbitrated",):
            stats["skipped"] += 1
            continue

        block = db.query(AnswerBlock).filter(AnswerBlock.id == result.block_id).first()
        image_bytes = _load_block_bytes(block)
        if image_bytes is None:
            stats["failed"] += 1
            continue

        config = config_map.get(result.question_number or "")
        context = {
            "question_number": result.question_number,
            "max_score": float(result.max_score or 0),
            "standard_answer": config.standard_answer if config else None,
            "scoring_points": config.scoring_points if config else None,
            "deduction_notes": config.deduction_notes if config else None,
            "prompt_template": config.prompt_template if config else None,
        }

        try:
            ai_result = provider.score_subjective(image_bytes, context)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI 评分失败 block=%s: %s", result.block_id, exc)
            stats["failed"] += 1
            continue

        result.ai_score = ai_result.score
        result.ai_comment = ai_result.comment
        result.ai_confidence = ai_result.confidence
        result.ai_model = ai_result.model
        result.ai_provider = ai_result.provider
        result.ai_detail = ai_result.detail
        result.ai_scored_at = datetime.now(timezone.utc)
        if result.grading_mode != "manual":
            result.status = "ai_scored"
        stats["scored"] += 1

        threshold = _confidence_threshold(config)
        low = ai_result.confidence < threshold
        if low:
            stats["low_confidence"] += 1
        _sync_ai_exception(db, exam, result, block, ai_result, low, threshold, source_cache)

        _log(db, exam_id, result.block_id, result.id, "ai_score", None,
             score_after=ai_result.score, operator_name=ai_result.provider,
             note=f"AI 预评 {ai_result.score} 分，置信度 {ai_result.confidence:.2f}",
             detail={"model": ai_result.model, "low_confidence": low})

    db.commit()
    realtime.publish_exam_event(exam_id, "grading_progress", progress(db, exam_id))
    return stats


def _sync_ai_exception(
    db: Session, exam: Exam, result: SubjectiveResult, block: Optional[AnswerBlock],
    ai_result: ai_service.AIScoreResult, low: bool, threshold: float,
    source_cache: Dict[UUID, str],
) -> None:
    """低置信度转异常复核；正常则清理旧的待处理 AI 异常。"""
    db.query(ExamException).filter(
        ExamException.block_id == result.block_id,
        ExamException.status == "pending",
        ExamException.exception_type.like(f"{AI_EXCEPTION_PREFIX}%"),
    ).delete(synchronize_session=False)

    if not low:
        return

    if result.page_id not in source_cache:
        page = db.query(ImportedPage).filter(ImportedPage.id == result.page_id).first()
        source_cache[result.page_id] = page.source_type if page else "pdf"

    db.add(ExamException(
        exam_id=exam.id,
        page_id=result.page_id,
        block_id=result.block_id,
        exception_type="ai_low_confidence",
        source=source_cache[result.page_id],
        status="pending",
        description=(
            f"第 {result.question_number or '-'} 题 AI 置信度 {ai_result.confidence:.2f} "
            f"低于阈值 {threshold:.2f}，需人工复核"
        ),
        snapshot_path=block.image_path if block else None,
    ))


# ---------------- 人工评分与仲裁 ----------------

def save_grade(
    db: Session,
    result_id: UUID,
    user_id: UUID,
    score: float,
    comment: Optional[str] = None,
    mark: Optional[str] = None,
) -> SubjectiveResult:
    """人工评分：按模式与当前状态决定记为一评、二评或直接终评。"""
    result = _get_result_or_404(db, result_id)
    max_score = float(result.max_score or 0)
    if score < 0 or (max_score and score > max_score):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"分数需在 0 ~ {max_score} 之间")
    if mark is not None:
        if mark not in ANSWER_MARK_VALUES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的作答标记")
        result.mark = mark

    now = datetime.now(timezone.utc)
    mode = result.grading_mode or "manual"
    is_second = (
        mode == "double"
        and result.first_score is not None
        and result.first_grader_id != user_id
    )

    if mode == "double" and is_second:
        before = result.final_score
        result.second_score = score
        result.second_comment = comment
        result.second_grader_id = user_id
        result.second_graded_at = now
        tolerance = _tolerance(db, result)
        diff = abs(float(result.first_score) - score)
        if diff > tolerance:
            result.status = "arbitrating"
            result.final_score = None
            action = "grade_second"
            note = f"二评 {score} 分，与一评差值 {diff:.2f} 超限（阈值 {tolerance:.2f}），转仲裁"
        else:
            result.final_score = round((float(result.first_score) + score) / 2, 2)
            result.status = "graded"
            action = "grade_second"
            note = f"二评 {score} 分，差值 {diff:.2f} 在阈值内，取平均终评 {result.final_score}"
        _log(db, result.exam_id, result.block_id, result.id, action, user_id,
             score_before=before, score_after=result.final_score, note=note,
             detail={"first_score": float(result.first_score), "second_score": score, "tolerance": tolerance})
    else:
        before = result.first_score
        result.first_score = score
        result.first_comment = comment
        result.first_grader_id = user_id
        result.first_graded_at = now
        if mode == "double":
            result.status = "graded_pending_second"
            result.final_score = None
            note = f"一评 {score} 分，等待二评"
        else:
            result.status = "graded"
            result.final_score = score
            note = f"人工评分 {score} 分"
        _log(db, result.exam_id, result.block_id, result.id, "grade_first", user_id,
             score_before=before, score_after=result.final_score, note=note,
             detail={"mode": mode})

    block = db.query(AnswerBlock).filter(AnswerBlock.id == result.block_id).first()
    if block:
        block.status = "scored"

    db.query(ExamException).filter(
        ExamException.block_id == result.block_id,
        ExamException.status == "pending",
        ExamException.exception_type.like(f"{AI_EXCEPTION_PREFIX}%"),
    ).update({
        ExamException.status: "resolved",
        ExamException.resolved_by: user_id,
        ExamException.resolved_at: now,
        ExamException.resolution_action: "subjective_grade",
        ExamException.resolution_note: f"人工评分 {score} 分",
    }, synchronize_session=False)

    db.commit()
    db.refresh(result)

    # 实时刷新阅卷进度；进入仲裁时提醒教务/教研处理
    realtime.publish_exam_event(result.exam_id, "grading_progress", progress(db, result.exam_id))
    if result.status == "arbitrating":
        notification_service.emit_event(
            "arbitration_required",
            content=f"第 {result.question_number or '-'} 题双评差值超限，需要仲裁",
            link=f"/grading?exam_id={result.exam_id}&tab=arbitration",
            recipient_roles=["exam_admin", "group_leader"],
            meta={"exam_id": str(result.exam_id), "result_id": str(result.id), "question_number": result.question_number},
            actor_id=user_id,
            db=db,
        )
    return result


def list_arbitration(db: Session, exam_id: UUID) -> List[SubjectiveResult]:
    """待仲裁列表：双评差值超限的任务。"""
    _get_exam_or_404(db, exam_id)
    return (
        db.query(SubjectiveResult)
        .filter(SubjectiveResult.exam_id == exam_id, SubjectiveResult.status == "arbitrating")
        .order_by(SubjectiveResult.question_number)
        .all()
    )


def arbitrate(
    db: Session, result_id: UUID, user_id: UUID, final_score: float, note: Optional[str] = None
) -> SubjectiveResult:
    """仲裁：给出终评分数，关闭仲裁状态。"""
    result = _get_result_or_404(db, result_id)
    if result.status != "arbitrating":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该任务当前不处于仲裁状态")
    max_score = float(result.max_score or 0)
    if final_score < 0 or (max_score and final_score > max_score):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"分数需在 0 ~ {max_score} 之间")

    before = result.final_score
    result.final_score = final_score
    result.arbiter_id = user_id
    result.arbitrated_at = datetime.now(timezone.utc)
    result.arbitration_note = note
    result.status = "arbitrated"

    _log(db, result.exam_id, result.block_id, result.id, "arbitrate", user_id,
         score_before=before, score_after=final_score,
         note=note or f"仲裁终评 {final_score} 分",
         detail={"first_score": float(result.first_score or 0), "second_score": float(result.second_score or 0)})
    db.commit()
    db.refresh(result)
    realtime.publish_exam_event(result.exam_id, "grading_progress", progress(db, result.exam_id))
    return result


# ---------------- 查询、进度与日志 ----------------

def list_tasks(
    db: Session,
    exam_id: UUID,
    status_filter: Optional[str] = None,
    question_number: Optional[str] = None,
    mine_user_id: Optional[UUID] = None,
) -> List[SubjectiveResult]:
    ensure_results(db, exam_id)
    query = db.query(SubjectiveResult).filter(SubjectiveResult.exam_id == exam_id)
    if status_filter:
        query = query.filter(SubjectiveResult.status == status_filter)
    if question_number:
        query = query.filter(SubjectiveResult.question_number == question_number)
    if mine_user_id:
        query = query.filter(SubjectiveResult.assigned_to == mine_user_id)
    return query.order_by(SubjectiveResult.question_number, SubjectiveResult.created_at).all()


def progress(db: Session, exam_id: UUID) -> dict:
    """阅卷进度看板：整体状态分布 + 每题维度统计。"""
    _get_exam_or_404(db, exam_id)
    results = ensure_results(db, exam_id)

    by_status: Dict[str, int] = {
        "pending": 0, "ai_scored": 0, "graded": 0,
        "graded_pending_second": 0, "arbitrating": 0, "arbitrated": 0,
    }
    by_question: Dict[str, dict] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        q = r.question_number or "-"
        group = by_question.setdefault(q, {"question_number": q, "total": 0, "graded": 0, "arbitrating": 0, "max_score": float(r.max_score or 0)})
        group["total"] += 1
        if r.status in ("graded", "arbitrated"):
            group["graded"] += 1
        if r.status == "arbitrating":
            group["arbitrating"] += 1

    total = len(results)
    done = by_status.get("graded", 0) + by_status.get("arbitrated", 0)
    return {
        "total": total,
        "done": done,
        "completion_rate": round(done / total, 4) if total else 0.0,
        "by_status": by_status,
        "by_question": [by_question[q] for q in sorted(by_question)],
    }


def list_logs(db: Session, exam_id: UUID, result_id: Optional[UUID] = None, limit: int = 200) -> List[GradingLog]:
    query = db.query(GradingLog).filter(GradingLog.exam_id == exam_id)
    if result_id:
        query = query.filter(GradingLog.result_id == result_id)
    return query.order_by(GradingLog.created_at.desc()).limit(limit).all()


# ---------------- 基础辅助 ----------------

def _get_exam_or_404(db: Session, exam_id: UUID) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


def _get_result_or_404(db: Session, result_id: UUID) -> SubjectiveResult:
    result = db.query(SubjectiveResult).filter(SubjectiveResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="阅卷任务不存在")
    return result


def _region_map(db: Session, exam: Exam) -> Dict[UUID, TemplateRegion]:
    if not exam.answer_card_template_id:
        return {}
    regions = (
        db.query(TemplateRegion)
        .filter(TemplateRegion.template_id == exam.answer_card_template_id)
        .all()
    )
    return {r.id: r for r in regions}


def _ai_config_map(db: Session, exam: Exam) -> Dict[str, AIScoringConfig]:
    """题号 -> AI 评分规则，考试级优先于模板级。"""
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


def _confidence_threshold(config: Optional[AIScoringConfig]) -> float:
    if config and config.confidence_threshold is not None:
        return float(config.confidence_threshold)
    return float(settings.LLM_CONFIDENCE_THRESHOLD)


def _tolerance(db: Session, result: SubjectiveResult) -> float:
    exam = db.query(Exam).filter(Exam.id == result.exam_id).first()
    if exam:
        config_map = _ai_config_map(db, exam)
        config = config_map.get(result.question_number or "")
        if config and config.score_tolerance is not None and float(config.score_tolerance) > 0:
            return float(config.score_tolerance)
    return DEFAULT_DOUBLE_TOLERANCE


def _load_block_bytes(block: Optional[AnswerBlock]) -> Optional[bytes]:
    if block is None or not block.image_path:
        return None
    path = absolute_path(block.image_path)
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError as exc:  # noqa: BLE001
        logger.warning("读取非选择题题块失败 block=%s: %s", block.id, exc)
        return None


def _log(
    db: Session,
    exam_id: UUID,
    block_id: Optional[UUID],
    result_id: Optional[UUID],
    action: str,
    operator_id: Optional[UUID],
    score_before: Optional[float] = None,
    score_after: Optional[float] = None,
    note: Optional[str] = None,
    operator_name: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    if operator_id is not None and operator_name is None:
        from app.models.user import User  # 局部导入避免循环

        user = db.query(User).filter(User.id == operator_id).first()
        operator_name = user.real_name or user.username if user else None
    db.add(GradingLog(
        exam_id=exam_id,
        block_id=block_id,
        result_id=result_id,
        action=action,
        operator_id=operator_id,
        operator_name=operator_name,
        score_before=score_before,
        score_after=score_after,
        note=note,
        detail=detail,
    ))