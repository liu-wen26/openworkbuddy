from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.db.base import get_db
from app.models.choice_result import ChoiceResult
from app.models.student import Student
from app.models.user import User
from app.schemas.choices import (
    ChoiceAnswerListOut,
    ChoiceAnswerSaveIn,
    ChoiceAnswerSaveOut,
    ChoiceGradeOut,
    ChoiceResultOut,
    ChoiceReviewIn,
    ChoiceStatisticsOut,
)
from app.services import choice_service

router = APIRouter(prefix="/choices", tags=["选择题判分"])


@router.post("/grade", response_model=ChoiceGradeOut)
def grade_choices(
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("choice:grade")),
):
    """对指定考试的全部选择题题块执行自动判分（保留已人工复核结果）。"""
    return choice_service.grade_exam_choices(db, exam_id)


@router.get("/results", response_model=List[ChoiceResultOut])
def list_results(
    exam_id: UUID = Query(...),
    status: Optional[str] = Query(default=None, pattern=r"^(scored|exception|reviewed)$"),
    student_id: Optional[UUID] = Query(default=None),
    question_number: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("choice:view")),
):
    results = choice_service.list_choice_results(
        db, exam_id, status_filter=status, student_id=student_id, question_number=question_number
    )
    return [_result_out(db, r) for r in results]


@router.post("/results/{result_id}/review", response_model=ChoiceResultOut)
def review_result(
    result_id: UUID,
    payload: ChoiceReviewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("choice:review")),
):
    """人工复核：指定正确的填涂选项，重新判定得分并关闭对应异常。"""
    result = choice_service.review_choice_result(db, result_id, payload.options, current_user.id, payload.note)
    return _result_out(db, result)


@router.get("/statistics", response_model=ChoiceStatisticsOut)
def statistics(
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("choice:view")),
):
    """选择题实时统计：整体概览 + 每题正确率与选项分布。"""
    return choice_service.choice_statistics(db, exam_id)


@router.get("/answers", response_model=ChoiceAnswerListOut)
def list_answers(
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("choice:view")),
):
    """列出该考试所有选择题的标准答案（考试级优先）。"""
    return choice_service.list_choice_answers(db, exam_id)


@router.put("/answers", response_model=ChoiceAnswerSaveOut)
def save_answers(
    payload: ChoiceAnswerSaveIn,
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("choice:grade")),
):
    """批量保存标准答案，并可选择保存后立即重新判分。"""
    items = [item.model_dump() for item in payload.items]
    return choice_service.save_choice_answers(db, exam_id, items, regrade=payload.regrade)


def _result_out(db: Session, result: ChoiceResult) -> ChoiceResultOut:
    out = ChoiceResultOut.model_validate(result)
    if result.student_id:
        student = db.query(Student).filter(Student.id == result.student_id).first()
        if student:
            out.student_name = student.name
            out.class_name = student.class_name
            out.exam_number = student.exam_number
    return out