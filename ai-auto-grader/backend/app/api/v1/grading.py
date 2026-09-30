from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.db.base import get_db
from app.models.student import Student
from app.models.subjective_result import SubjectiveResult
from app.models.user import User
from app.schemas.grading import (
    GradingAIScoreOut,
    GradingArbitrateIn,
    GradingDistributeIn,
    GradingDistributeOut,
    GradingGradeIn,
    GradingLogOut,
    GradingProgressOut,
    GradingTaskOut,
)
from app.services import subjective_service

router = APIRouter(prefix="/grading", tags=["非选择题阅卷"])


@router.post("/distribute", response_model=GradingDistributeOut)
def distribute(
    payload: GradingDistributeIn,
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:distribute")),
):
    """阅卷任务分发：设置阅卷模式并（可选）指定阅卷人。"""
    return subjective_service.distribute(
        db, exam_id, payload.mode, current_user.id, payload.assign_to, payload.question_numbers
    )


@router.post("/ai-score", response_model=GradingAIScoreOut)
def ai_score(
    exam_id: UUID = Query(...),
    force: bool = Query(default=False, description="为 true 时对已预评题目覆盖重跑"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:ai")),
):
    """对非选择题执行 AI 预评（幂等：已人工评分或已预评的任务默认跳过，可用 force 覆盖重跑）。"""
    return subjective_service.run_ai_scoring(db, exam_id, force=force)


@router.get("/tasks", response_model=List[GradingTaskOut])
def list_tasks(
    exam_id: UUID = Query(...),
    status: Optional[str] = Query(default=None),
    question_number: Optional[str] = Query(default=None),
    mine: bool = Query(default=False, description="仅返回分配给我的任务"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:grade")),
):
    """阅卷任务队列（可按状态、题号、是否分配给我筛选）。"""
    results = subjective_service.list_tasks(
        db, exam_id, status_filter=status, question_number=question_number,
        mine_user_id=current_user.id if mine else None,
    )
    return [_task_out(db, r) for r in results]


@router.get("/tasks/{result_id}", response_model=GradingTaskOut)
def get_task(
    result_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:grade")),
):
    result = subjective_service._get_result_or_404(db, result_id)
    return _task_out(db, result)


@router.post("/tasks/{result_id}/grade", response_model=GradingTaskOut)
def grade_task(
    result_id: UUID,
    payload: GradingGradeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:grade")),
):
    """人工评分：双评模式下自动区分为一评/二评。"""
    result = subjective_service.save_grade(
        db, result_id, current_user.id, payload.score, payload.comment, payload.mark
    )
    return _task_out(db, result)


@router.get("/arbitration", response_model=List[GradingTaskOut])
def list_arbitration(
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:arbitrate")),
):
    """待仲裁列表（双评差值超限）。"""
    results = subjective_service.list_arbitration(db, exam_id)
    return [_task_out(db, r) for r in results]


@router.post("/arbitration/{result_id}", response_model=GradingTaskOut)
def arbitrate(
    result_id: UUID,
    payload: GradingArbitrateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:arbitrate")),
):
    """仲裁：给出终评分数。"""
    result = subjective_service.arbitrate(db, result_id, current_user.id, payload.final_score, payload.note)
    return _task_out(db, result)


@router.get("/progress", response_model=GradingProgressOut)
def progress(
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:view_all")),
):
    """阅卷进度看板。"""
    return subjective_service.progress(db, exam_id)


@router.get("/logs", response_model=List[GradingLogOut])
def logs(
    exam_id: UUID = Query(...),
    result_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("scoring:log")),
):
    """阅卷痕迹日志。"""
    return subjective_service.list_logs(db, exam_id, result_id=result_id)


def _task_out(db: Session, result: SubjectiveResult) -> GradingTaskOut:
    out = GradingTaskOut.model_validate(result)
    if result.student_id:
        student = db.query(Student).filter(Student.id == result.student_id).first()
        if student:
            out.student_name = student.name
            out.class_name = student.class_name
            out.exam_number = student.exam_number
    return out