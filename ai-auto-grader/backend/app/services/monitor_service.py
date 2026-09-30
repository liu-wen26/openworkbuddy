"""阅卷进度监控服务（F9-02）。

以考试为粒度汇总「选择题判分 / 非选择题阅卷 / 异常处理 / 导入」的完成度，
用于教研组长与教务的全局监控看板。仅做只读统计，不产生副作用。
"""

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.choice_result import ChoiceResult
from app.models.exam import Exam
from app.models.exception import ExamException
from app.models.import_batch import ImportBatch
from app.models.subjective_result import SubjectiveResult


def _choice_progress(db: Session, exam_id: UUID) -> dict:
    rows = (
        db.query(ChoiceResult.status, func.count(ChoiceResult.id))
        .filter(ChoiceResult.exam_id == exam_id)
        .group_by(ChoiceResult.status)
        .all()
    )
    by_status = {s: c for s, c in rows}
    total = sum(by_status.values())
    correct = db.query(func.count(ChoiceResult.id)).filter(
        ChoiceResult.exam_id == exam_id, ChoiceResult.is_correct.is_(True)
    ).scalar() or 0
    exception = by_status.get("exception", 0)
    graded = total - exception
    return {
        "total": total,
        "graded": graded,
        "exception": exception,
        "reviewed": by_status.get("reviewed", 0),
        "correct": correct,
        "correct_rate": round(correct / graded, 4) if graded else 0.0,
        "completion_rate": round(graded / total, 4) if total else 0.0,
    }


def _subjective_progress(db: Session, exam_id: UUID) -> dict:
    rows = (
        db.query(SubjectiveResult.status, func.count(SubjectiveResult.id))
        .filter(SubjectiveResult.exam_id == exam_id)
        .group_by(SubjectiveResult.status)
        .all()
    )
    by_status: Dict[str, int] = {
        "pending": 0, "ai_scored": 0, "graded": 0,
        "graded_pending_second": 0, "arbitrating": 0, "arbitrated": 0,
    }
    for s, c in rows:
        by_status[s] = by_status.get(s, 0) + c
    total = sum(by_status.values())
    done = by_status.get("graded", 0) + by_status.get("arbitrated", 0)
    ai_scored = by_status.get("ai_scored", 0)
    return {
        "total": total,
        "done": done,
        "arbitrating": by_status.get("arbitrating", 0),
        "by_status": by_status,
        "completion_rate": round(done / total, 4) if total else 0.0,
        "ai_scored": ai_scored,
        "ai_pending_review": ai_scored,
        "ai_pending_rate": round(ai_scored / total, 4) if total else 0.0,
        "finished_rate": round((done + ai_scored) / total, 4) if total else 0.0,
    }


def _exception_progress(db: Session, exam_id: UUID) -> dict:
    rows = (
        db.query(ExamException.status, func.count(ExamException.id))
        .filter(ExamException.exam_id == exam_id)
        .group_by(ExamException.status)
        .all()
    )
    by_status = {s: c for s, c in rows}
    total = sum(by_status.values())
    resolved = by_status.get("resolved", 0) + by_status.get("ignored", 0)
    return {
        "total": total,
        "pending": by_status.get("pending", 0),
        "resolved": resolved,
        "by_status": by_status,
        "completion_rate": round(resolved / total, 4) if total else 0.0,
    }


def _import_progress(db: Session, exam_id: UUID) -> dict:
    batches = db.query(ImportBatch).filter(ImportBatch.exam_id == exam_id).all()
    return {
        "batch_count": len(batches),
        "page_count": sum(int(b.total_pages or 0) for b in batches),
        "processed_pages": sum(int(b.processed_pages or 0) for b in batches),
    }


def exam_progress(db: Session, exam_id: UUID) -> dict:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")

    choice = _choice_progress(db, exam_id)
    subjective = _subjective_progress(db, exam_id)
    exception = _exception_progress(db, exam_id)
    imports = _import_progress(db, exam_id)

    # 综合完成度：选择题 + 非选择题 加权
    quota = choice["total"] + subjective["total"]
    finished = choice["graded"] + subjective["done"]
    return {
        "exam_id": exam.id,
        "exam_name": exam.name,
        "subject": exam.subject,
        "grade": exam.grade,
        "status": exam.status,
        "choice": choice,
        "subjective": subjective,
        "exception": exception,
        "imports": imports,
        "overall_completion": round(finished / quota, 4) if quota else 0.0,
    }


def list_exam_progress(db: Session, exam_status: Optional[str] = None) -> List[dict]:
    query = db.query(Exam)
    if exam_status:
        query = query.filter(Exam.status == exam_status)
    exams = query.order_by(Exam.created_at.desc()).all()

    results = []
    for exam in exams:
        choice = _choice_progress(db, exam.id)
        subjective = _subjective_progress(db, exam.id)
        exception = _exception_progress(db, exam.id)
        quota = choice["total"] + subjective["total"]
        finished = choice["graded"] + subjective["done"]
        results.append({
            "exam_id": exam.id,
            "exam_name": exam.name,
            "subject": exam.subject,
            "grade": exam.grade,
            "status": exam.status,
            "choice_total": choice["total"],
            "choice_graded": choice["graded"],
            "subjective_total": subjective["total"],
            "subjective_done": subjective["done"],
            "arbitrating": subjective["arbitrating"],
            "exception_pending": exception["pending"],
            "overall_completion": round(finished / quota, 4) if quota else 0.0,
        })
    return results