"""选择题自动判分服务（F6 系列）。

职责：
1. 依据模板渲染时的精确网格几何，对每个选择题题块做 OMR 填涂识别；
2. 结合标准答案自动打分，并判定多涂 / 漏涂 / 模糊等异常；
3. 提供人工复核与统计（正确率、选项分布）能力。

异常与正常判分共用同一套题块数据（answer_blocks），结果写入 choice_results。
"""

import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.answer_block import AnswerBlock
from app.models.choice_result import ChoiceResult
from app.models.exam import Exam
from app.models.exception import ExamException
from app.models.imported_page import ImportedPage
from app.models.template import AnswerCardTemplate
from app.models.template_config import ChoiceAnswer, TemplateRegion
from app.services.template_service import PAPER_SIZES
from app.utils import image as image_utils
from app.utils import omr
from app.utils.file_storage import absolute_path

logger = logging.getLogger(__name__)
settings = get_settings()

# 与 template_service._draw_choice_bubbles 保持一致的布局常量（单位 pt）
CHOICE_GRID = {
    "cx": 16.0,            # 选项圆圈中心距区域左边距离
    "start_y": 26.0,       # 首个选项圆圈中心距区域上边距离
    "bubble_radius": 5.0,  # 圆圈半径
    "top_pad": 30.0,       # gap 计算中的上边留白
    "min_gap": 10.0,
    "bottom_pad": 4.0,
}

EXCEPTION_TYPES = {
    "missing_fill": "选择题未填涂",
    "multi_fill": "选择题多涂",
    "ambiguous": "选择题填涂模糊，无法确定",
    "unreadable": "选择题填涂无法识别",
    "no_answer_key": "该题未配置标准答案",
}
CHOICE_EXCEPTION_PREFIX = "choice_"


# ---------------- 判分主流程 ----------------

def grade_exam_choices(db: Session, exam_id: UUID, only_block_ids: Optional[List[UUID]] = None) -> dict:
    """对某场考试的全部（或指定）选择题题块执行自动判分。

    已人工复核（status=reviewed）的结果会被保留，不会被覆盖。
    返回统计：{graded, scored, exception, skipped}。
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    template = (
        db.query(AnswerCardTemplate).filter(AnswerCardTemplate.id == exam.answer_card_template_id).first()
        if exam.answer_card_template_id else None
    )
    if not template:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="考试未绑定答题卡模板")

    regions = db.query(TemplateRegion).filter(TemplateRegion.template_id == template.id).all()
    region_map = {r.id: r for r in regions}
    answer_map = _build_answer_map(db, exam_id, template.id)

    blocks = (
        db.query(AnswerBlock)
        .filter(AnswerBlock.exam_id == exam_id, AnswerBlock.block_type == "choice")
        .all()
    )
    if only_block_ids:
        wanted = set(only_block_ids)
        blocks = [b for b in blocks if b.id in wanted]

    source_cache: Dict[UUID, str] = {}
    stats = {"graded": 0, "scored": 0, "exception": 0, "skipped": 0}

    for block in blocks:
        existing = db.query(ChoiceResult).filter(ChoiceResult.block_id == block.id).first()
        if existing and existing.status == "reviewed":
            stats["skipped"] += 1
            continue

        region = region_map.get(block.region_id)
        if not region:
            stats["skipped"] += 1
            continue

        answer = answer_map.get(block.question_number or "")
        result = _grade_block(db, exam, template, region, block, answer, source_cache)
        stats["graded"] += 1
        stats["exception" if result.status == "exception" else "scored"] += 1

    db.commit()
    return stats


def _grade_block(
    db: Session,
    exam: Exam,
    template: AnswerCardTemplate,
    region: TemplateRegion,
    block: AnswerBlock,
    answer: Optional[ChoiceAnswer],
    source_cache: Dict[UUID, str],
) -> ChoiceResult:
    options_count = int(region.options_count or 4)
    allow_multiple = bool(region.allow_multiple)
    correct_options = (answer.correct_options if answer else None) or ""
    max_score = float(region.max_score or 0) or float(answer.score if answer and answer.score else 0)

    # 1. 读取题块图像并识别
    image = _load_block_image(block)
    if image is None:
        rec = {"options": "", "ratios": [0.0] * options_count, "confidence": 0.0, "status": "unreadable"}
    else:
        grid = _choice_grid(template, region)
        rec = omr.recognize_choice(
            image,
            options_count=options_count,
            fill_threshold=settings.OMR_FILL_THRESHOLD,
            option_x_fraction=grid[0] if grid else None,
            option_y_fractions=grid[1] if grid else None,
            bubble_radius_fraction=grid[2] if grid else 0.02,
        )

    # 2. 判定状态与异常类型
    result_status = "scored"
    exception_type: Optional[str] = None
    if not correct_options:
        exception_type = "no_answer_key"
    elif rec["status"] == "blank":
        exception_type = "missing_fill"
    elif rec["status"] == "unreadable":
        exception_type = "unreadable"
    elif rec["status"] == "ambiguous":
        exception_type = "ambiguous"
    elif rec["status"] == "multi" and not allow_multiple:
        exception_type = "multi_fill"
    if exception_type:
        result_status = "exception"

    # 3. 计分（异常结果先按 0 分占位，人工复核后修正）
    if result_status == "scored":
        is_correct, score = _evaluate(
            rec["options"], correct_options, max_score, allow_multiple, region.partial_score_rules
        )
    else:
        is_correct, score = False, 0.0

    # 4. 写入/更新结果
    result = db.query(ChoiceResult).filter(ChoiceResult.block_id == block.id).first()
    if not result:
        result = ChoiceResult(exam_id=exam.id, block_id=block.id, page_id=block.page_id)
        db.add(result)

    result.student_id = block.student_id
    result.region_id = region.id
    result.question_number = block.question_number or ""
    result.recognized_options = rec["options"]
    result.correct_options = correct_options
    result.is_correct = is_correct
    result.score = score
    result.max_score = max_score
    result.status = result_status
    result.exception_type = exception_type
    result.confidence = rec["confidence"]
    result.fill_ratios = rec["ratios"]

    block.status = "exception" if result_status == "exception" else "scored"

    # 5. 生成/清理异常记录（幂等）
    _sync_exception(db, exam, block, region, answer, result, exception_type, source_cache, options_count)
    db.flush()
    return result


def _sync_exception(
    db: Session,
    exam: Exam,
    block: AnswerBlock,
    region: TemplateRegion,
    answer: Optional[ChoiceAnswer],
    result: ChoiceResult,
    exception_type: Optional[str],
    source_cache: Dict[UUID, str],
    options_count: int,
) -> None:
    """按最新判分结果同步异常记录：非异常则清理旧的待处理选择题异常。"""
    db.query(ExamException).filter(
        ExamException.block_id == block.id,
        ExamException.status == "pending",
        ExamException.exception_type.like(f"{CHOICE_EXCEPTION_PREFIX}%"),
    ).delete(synchronize_session=False)

    if not exception_type:
        return

    if block.page_id not in source_cache:
        page = db.query(ImportedPage).filter(ImportedPage.id == block.page_id).first()
        source_cache[block.page_id] = page.source_type if page else "pdf"

    detail = EXCEPTION_TYPES.get(exception_type, exception_type)
    if exception_type == "no_answer_key":
        description = f"第 {block.question_number or '-'} 题{detail}"
    elif exception_type == "missing_fill":
        description = f"第 {block.question_number or '-'} 题未填涂"
    elif exception_type == "multi_fill":
        description = f"第 {block.question_number or '-'} 题多涂：{result.recognized_options}"
    elif exception_type in ("ambiguous", "unreadable"):
        description = f"第 {block.question_number or '-'} 题{detail}"
    else:
        description = detail

    db.add(ExamException(
        exam_id=exam.id,
        page_id=block.page_id,
        block_id=block.id,
        exception_type=f"{CHOICE_EXCEPTION_PREFIX}{exception_type}",
        source=source_cache[block.page_id],
        status="pending",
        description=description,
        snapshot_path=block.image_path,
    ))


def _evaluate(
    recognized: Optional[str],
    correct: Optional[str],
    max_score: float,
    allow_multiple: bool,
    partial_rules,
) -> tuple[bool, float]:
    """比对作答与标准答案，返回 (是否全对, 得分)。"""
    rec = set((recognized or "").upper())
    cor = set((correct or "").upper())
    if not cor:
        return False, 0.0
    if rec == cor:
        return True, float(max_score)
    # 多选题：作答是标准答案的真子集时可按比例给分
    if allow_multiple and rec and rec < cor:
        ratio = 0.5
        if isinstance(partial_rules, dict):
            ratio = float(partial_rules.get("ratio", 0.5))
        return False, round(float(max_score) * ratio, 2)
    return False, 0.0


# ---------------- 人工复核 ----------------

def review_choice_result(
    db: Session, result_id: UUID, options: str, user_id: UUID, note: Optional[str] = None
) -> ChoiceResult:
    """人工复核：以指定选项重新判定该题结果，并关闭对应异常。"""
    result = db.query(ChoiceResult).filter(ChoiceResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="选择题判分结果不存在")

    region = db.query(TemplateRegion).filter(TemplateRegion.id == result.region_id).first()
    allow_multiple = bool(region.allow_multiple) if region else False
    partial_rules = region.partial_score_rules if region else None

    normalized = "".join(sorted({c for c in (options or "").upper() if c.isalpha()}))
    is_correct, score = _evaluate(
        normalized, result.correct_options, float(result.max_score or 0), allow_multiple, partial_rules
    )

    result.recognized_options = normalized
    result.is_correct = is_correct
    result.score = score
    result.status = "reviewed"
    result.exception_type = None
    result.reviewed_by = user_id
    result.reviewed_at = datetime.now(timezone.utc)
    result.review_note = note

    block = db.query(AnswerBlock).filter(AnswerBlock.id == result.block_id).first()
    if block:
        block.status = "scored"

    db.query(ExamException).filter(
        ExamException.block_id == result.block_id,
        ExamException.status == "pending",
        ExamException.exception_type.like(f"{CHOICE_EXCEPTION_PREFIX}%"),
    ).update({
        ExamException.status: "resolved",
        ExamException.resolved_by: user_id,
        ExamException.resolved_at: datetime.now(timezone.utc),
        ExamException.resolution_action: "choice_review",
        ExamException.resolution_note: f"人工复核为 {normalized or '未填涂'}",
    }, synchronize_session=False)

    db.commit()
    db.refresh(result)
    return result


# ---------------- 标准答案维护 ----------------

def _normalize_options(value: Optional[str], options_count: int) -> str:
    """规范化选项：转大写、去重、按字母序，并过滤超出选项范围的字符。"""
    limit = max(1, int(options_count or 4))
    allowed = {chr(ord("A") + i) for i in range(limit)}
    return "".join(sorted({c for c in (value or "").upper() if c in allowed}))


def list_choice_answers(db: Session, exam_id: UUID) -> dict:
    """列出该考试所有选择题的标准答案（考试级优先，其次模板级，最后为空）。"""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    template = (
        db.query(AnswerCardTemplate).filter(AnswerCardTemplate.id == exam.answer_card_template_id).first()
        if exam.answer_card_template_id else None
    )
    if not template:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="考试未绑定答题卡模板")

    regions = (
        db.query(TemplateRegion)
        .filter(TemplateRegion.template_id == template.id, TemplateRegion.region_type == "choice")
        .all()
    )
    rows = db.query(ChoiceAnswer).filter(ChoiceAnswer.template_id == template.id).all()
    template_level = {r.question_number: r for r in rows if r.exam_id is None}
    exam_level = {r.question_number: r for r in rows if r.exam_id == exam_id}

    items: List[dict] = []
    for reg in sorted(regions, key=lambda r: _question_sort_key(r.question_number or "")):
        qn = reg.question_number or ""
        options_count = int(reg.options_count or 4)
        answer = exam_level.get(qn) or template_level.get(qn)
        source = "none"
        if qn in exam_level:
            source = "exam"
        elif qn in template_level:
            source = "template"
        default_score = float(reg.max_score or 0)
        items.append({
            "question_number": qn,
            "options_count": options_count,
            "allow_multiple": bool(reg.allow_multiple),
            "max_score": default_score,
            "correct_options": (answer.correct_options or "") if answer else "",
            "score": float(answer.score) if answer and answer.score is not None else default_score,
            "source": source,
        })
    return {"template_id": template.id, "items": items}


def save_choice_answers(
    db: Session, exam_id: UUID, items: List[dict], regrade: bool = True
) -> dict:
    """批量保存考试级标准答案（按题号 upsert），可选保存后立即重新判分。"""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    template = (
        db.query(AnswerCardTemplate).filter(AnswerCardTemplate.id == exam.answer_card_template_id).first()
        if exam.answer_card_template_id else None
    )
    if not template:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="考试未绑定答题卡模板")

    regions = (
        db.query(TemplateRegion)
        .filter(TemplateRegion.template_id == template.id, TemplateRegion.region_type == "choice")
        .all()
    )
    region_map = {r.question_number: r for r in regions}

    for item in items:
        qn = (item.get("question_number") or "").strip()
        reg = region_map.get(qn)
        if reg is None:
            continue
        options_count = int(reg.options_count or 4)
        row = (
            db.query(ChoiceAnswer)
            .filter(
                ChoiceAnswer.exam_id == exam_id,
                ChoiceAnswer.template_id == template.id,
                ChoiceAnswer.question_number == qn,
            )
            .first()
        )
        if not row:
            row = ChoiceAnswer(exam_id=exam_id, template_id=template.id, question_number=qn)
            db.add(row)
        row.correct_options = _normalize_options(item.get("correct_options"), options_count)
        score = item.get("score")
        row.score = float(score) if score is not None else float(reg.max_score or 0)

    db.commit()

    grade_stats = grade_exam_choices(db, exam_id) if regrade else None
    data = list_choice_answers(db, exam_id)
    data["grade"] = grade_stats
    return data


# ---------------- 查询与统计 ----------------

def list_choice_results(
    db: Session,
    exam_id: UUID,
    status_filter: Optional[str] = None,
    student_id: Optional[UUID] = None,
    question_number: Optional[str] = None,
) -> List[ChoiceResult]:
    query = db.query(ChoiceResult).filter(ChoiceResult.exam_id == exam_id)
    if status_filter:
        query = query.filter(ChoiceResult.status == status_filter)
    if student_id:
        query = query.filter(ChoiceResult.student_id == student_id)
    if question_number:
        query = query.filter(ChoiceResult.question_number == question_number)
    return query.all()


def choice_statistics(db: Session, exam_id: UUID) -> dict:
    """按题目维度统计正确率与选项分布，并给出整体概览。"""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")

    results = db.query(ChoiceResult).filter(ChoiceResult.exam_id == exam_id).all()

    question_meta: Dict[str, dict] = {}
    if exam.answer_card_template_id:
        regions = (
            db.query(TemplateRegion)
            .filter(TemplateRegion.template_id == exam.answer_card_template_id, TemplateRegion.region_type == "choice")
            .all()
        )
        for r in regions:
            if not r.question_number:
                continue
            question_meta[r.question_number] = {
                "options_count": int(r.options_count or 4),
                "allow_multiple": bool(r.allow_multiple),
                "max_score": float(r.max_score or 0),
            }

    groups: "OrderedDict[str, dict]" = OrderedDict()
    for q in sorted(question_meta.keys(), key=_question_sort_key):
        groups[q] = _new_group(q, question_meta[q])
    for r in results:
        q = r.question_number or "-"
        if q not in groups:
            groups[q] = _new_group(q, {"options_count": 4, "allow_multiple": False, "max_score": float(r.max_score or 0)})
        group = groups[q]
        group["total"] += 1
        group["score_sum"] += float(r.score or 0)
        answered = r.status != "exception"
        if answered:
            group["graded"] += 1
            if r.is_correct:
                group["correct"] += 1
        else:
            group["exception"] += 1
        for ch in (r.recognized_options or ""):
            group["distribution"][ch] = group["distribution"].get(ch, 0) + 1

    questions = []
    for q, g in groups.items():
        letters = [chr(ord("A") + i) for i in range(g["options_count"])]
        graded = g["graded"]
        correct_rate = round(g["correct"] / graded, 4) if graded else 0.0
        questions.append({
            "question_number": q,
            "options_count": g["options_count"],
            "allow_multiple": g["allow_multiple"],
            "max_score": g["max_score"],
            "total": g["total"],
            "graded": graded,
            "correct": g["correct"],
            "exception": g["exception"],
            "correct_rate": correct_rate,
            "avg_score": round(g["score_sum"] / g["total"], 2) if g["total"] else 0.0,
            "distribution": {letter: g["distribution"].get(letter, 0) for letter in letters},
        })

    total_results = len(results)
    total_graded = sum(1 for r in results if r.status != "exception")
    total_correct = sum(1 for r in results if r.is_correct)
    total_exception = sum(1 for r in results if r.status == "exception")
    total_reviewed = sum(1 for r in results if r.status == "reviewed")
    score_sum = sum(float(r.score or 0) for r in results)

    overall = {
        "total_questions": len(questions),
        "total_results": total_results,
        "graded": total_graded,
        "exception": total_exception,
        "reviewed": total_reviewed,
        "correct": total_correct,
        "correct_rate": round(total_correct / total_graded, 4) if total_graded else 0.0,
        "avg_score": round(score_sum / total_results, 2) if total_results else 0.0,
    }
    return {"overall": overall, "questions": questions}


def _new_group(question_number: str, meta: dict) -> dict:
    return {
        "question_number": question_number,
        "options_count": meta.get("options_count", 4),
        "allow_multiple": meta.get("allow_multiple", False),
        "max_score": float(meta.get("max_score", 0) or 0),
        "total": 0,
        "graded": 0,
        "correct": 0,
        "exception": 0,
        "score_sum": 0.0,
        "distribution": {},
    }


def _question_sort_key(value: str):
    try:
        return (0, float(value), value)
    except (TypeError, ValueError):
        return (1, 0.0, value)


# ---------------- 基础辅助 ----------------

def _build_answer_map(db: Session, exam_id: UUID, template_id: UUID) -> Dict[str, ChoiceAnswer]:
    """构建题号 -> 标准答案映射，考试级答案优先于模板级。"""
    rows = (
        db.query(ChoiceAnswer)
        .filter(ChoiceAnswer.template_id == template_id)
        .all()
    )
    answer_map: Dict[str, ChoiceAnswer] = {}
    for r in rows:
        if r.exam_id is None:
            answer_map.setdefault(r.question_number, r)
    for r in rows:
        if r.exam_id == exam_id:
            answer_map[r.question_number] = r
    return answer_map


def _choice_grid(template: AnswerCardTemplate, region: TemplateRegion):
    """还原选择题选项圆圈在区域内的相对位置（0~1）。

    与 template_service._draw_choice_bubbles 使用同一套布局常量，
    保证按模板打印的答题卡能够被精确采样。
    返回 (选项中心x比例, [各选项中心y比例], 采样半径比例)。
    """
    page_w, page_h = PAPER_SIZES.get(template.paper_size, PAPER_SIZES["A4"])
    region_w_pt = float(region.width) / 1000.0 * page_w
    region_h_pt = float(region.height) / 1000.0 * page_h
    options = int(region.options_count or 4)
    if region_w_pt <= 20 or region_h_pt <= 0 or options < 2:
        return None

    gap = max(CHOICE_GRID["min_gap"], (region_h_pt - CHOICE_GRID["top_pad"]) / options)
    y_fractions: List[float] = []
    for i in range(options):
        cy = CHOICE_GRID["start_y"] + i * gap
        if cy > region_h_pt - CHOICE_GRID["bottom_pad"]:
            break
        y_fractions.append(cy / region_h_pt)
    if len(y_fractions) != options:
        return None

    x_fraction = CHOICE_GRID["cx"] / region_w_pt
    radius_fraction = (CHOICE_GRID["bubble_radius"] * 0.5) / region_h_pt
    return x_fraction, y_fractions, radius_fraction


def _load_block_image(block: AnswerBlock):
    if not block.image_path:
        return None
    path = absolute_path(block.image_path)
    if not path.exists():
        return None
    try:
        return image_utils.load_image(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取选择题题块失败 block=%s: %s", block.id, exc)
        return None