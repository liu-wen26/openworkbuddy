"""考试归档 API（F10-04）。"""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.db.base import get_db
from app.models.user import User
from app.services import archive_service, audit_service

router = APIRouter(prefix="/archives", tags=["考试归档"])


def _serialize(archive) -> dict:
    return {
        "id": archive.id,
        "exam_id": archive.exam_id,
        "exam_name": archive.exam_name,
        "status": archive.status,
        "previous_status": archive.previous_status,
        "file_size": archive.file_size,
        "original_paper_included": archive.original_paper_included,
        "snapshot": archive.snapshot,
        "created_by": archive.created_by,
        "created_at": archive.created_at,
        "restored_at": archive.restored_at,
    }


@router.post("/exams/{exam_id}")
def create_archive(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("archive:create")),
):
    archive = archive_service.create_archive(db, exam_id, current_user)
    audit_service.record_action(db, current_user, "archive", "archive",
                                {"exam_id": str(exam_id), "archive_id": str(archive.id)})
    return _serialize(archive)


@router.get("")
def list_archives(
    include_restored: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("archive:view")),
):
    return [_serialize(a) for a in archive_service.list_archives(db, include_restored)]


@router.get("/{archive_id}/download")
def download_archive(
    archive_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("archive:view")),
):
    archive = archive_service.get_archive_or_404(db, archive_id)
    content, filename = archive_service.get_bundle(archive)
    audit_service.record_action(db, current_user, "export", "archive",
                                {"archive_id": str(archive_id), "filename": filename})
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/{archive_id}/restore")
def restore_archive(
    archive_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("archive:create")),
):
    archive = archive_service.restore_archive(db, archive_id, current_user)
    audit_service.record_action(db, current_user, "archive_restore", "archive", {"archive_id": str(archive_id)})
    return _serialize(archive)


@router.delete("/{archive_id}", status_code=204)
def delete_archive(
    archive_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("archive:delete")),
):
    archive_service.delete_archive(db, archive_id)
    audit_service.record_action(db, current_user, "archive_delete", "archive", {"archive_id": str(archive_id)})
    return None