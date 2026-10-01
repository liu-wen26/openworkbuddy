"""导出 API（F10 系列）：成绩明细、学情报表、答卷/错题图片。"""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.db.base import get_db
from app.models.user import User
from app.services import audit_service, export_service

router = APIRouter(prefix="/exports", tags=["导出"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _attachment(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/exams/{exam_id}/grade-detail")
def export_grade_detail(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("export:download")),
):
    """F10-01 成绩明细表导出 Excel。"""
    content, filename = export_service.build_grade_detail(db, exam_id)
    audit_service.record_action(db, current_user, "export", "export",
                                {"exam_id": str(exam_id), "type": "grade_detail", "filename": filename})
    return _attachment(content, filename, XLSX_MIME)


@router.get("/exams/{exam_id}/report")
def export_report(
    exam_id: UUID,
    format: str = Query("xlsx", pattern="^(xlsx|html)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("export:download")),
):
    """F10-03 学情报表导出：xlsx 多表 / 可打印 HTML（另存为 PDF）。"""
    if format == "html":
        content, filename = export_service.build_report_html(db, exam_id)
        media_type = "text/html; charset=utf-8"
    else:
        content, filename = export_service.build_report_workbook(db, exam_id)
        media_type = XLSX_MIME
    audit_service.record_action(db, current_user, "export", "export",
                                {"exam_id": str(exam_id), "type": f"report_{format}", "filename": filename})
    return _attachment(content, filename, media_type)


@router.get("/exams/{exam_id}/answer-images")
def export_answer_images(
    exam_id: UUID,
    student_id: UUID | None = None,
    question_number: str | None = None,
    mark: str | None = Query(None, pattern="^(excellent|typical_error|blank)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("export:download")),
):
    """F10-02 答卷/错题图片导出（zip，含 manifest.csv，按需叠加水印）。"""
    content, filename = export_service.build_answer_images_zip(
        db, exam_id, student_id=student_id, question_number=question_number, mark=mark,
    )
    audit_service.record_action(db, current_user, "export", "export",
                                {"exam_id": str(exam_id), "type": "answer_images", "filename": filename})
    return _attachment(content, filename, "application/zip")