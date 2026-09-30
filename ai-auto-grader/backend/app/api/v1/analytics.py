"""学情分析报表 API（F8 系列）。"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.db.base import get_db
from app.models.user import User
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["学情分析"])


@router.get("/exams/{exam_id}/overview")
def overview(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics:view")),
):
    """F8-01 年级整场考试总览。"""
    return analytics_service.overview(db, exam_id)


@router.get("/exams/{exam_id}/classes")
def class_report(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics:view")),
):
    """F8-02 分班级学情报表。"""
    return analytics_service.class_report(db, exam_id)


@router.get("/exams/{exam_id}/questions")
def question_report(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics:view")),
):
    """F8-03 题目维度分析。"""
    return analytics_service.question_report(db, exam_id)


@router.get("/exams/{exam_id}/knowledge")
def knowledge_report(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics:view")),
):
    """F8-04 知识点掌握情况。"""
    return analytics_service.knowledge_report(db, exam_id)


@router.get("/exams/{exam_id}/students")
def list_students(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics:view")),
):
    """学生列表（供个人报告选择）。"""
    return analytics_service.list_students(db, exam_id)


@router.get("/exams/{exam_id}/students/{student_id}")
def student_report(
    exam_id: UUID,
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics:view")),
):
    """F8-05 学生个人学情报告。"""
    return analytics_service.student_report(db, exam_id, student_id)


@router.get("/exams/{exam_id}/review-materials")
def review_materials(
    exam_id: UUID,
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics:view")),
):
    """F8-06 讲评素材导出。"""
    return analytics_service.review_materials(db, exam_id, limit=limit)