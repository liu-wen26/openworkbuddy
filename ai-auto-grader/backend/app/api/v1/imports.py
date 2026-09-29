from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import require_permission
from app.db.base import get_db
from app.models.answer_block import AnswerBlock
from app.models.exception import ExamException
from app.models.exam import Exam
from app.models.import_batch import ImportBatch
from app.models.imported_page import ImportedPage
from app.models.student import Student
from app.models.user import User
from app.schemas.imports import (
    AnswerBlockOut,
    ExceptionOut,
    ExceptionUpdate,
    ImportBatchCreate,
    ImportBatchOut,
    ImportProgressOut,
    ImportedPageOut,
    ImportUploadResult,
    ManualExamNumberIn,
    RecutIn,
)
from app.services import import_service
from app.tasks.import_tasks import dispatch_process_batch
from app.utils.file_storage import absolute_path

router = APIRouter(prefix="/imports", tags=["Imports"])
settings = get_settings()


# ---------------- 批次 ----------------

@router.post("/batches", response_model=ImportBatchOut)
def create_batch(
    payload: ImportBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:create")),
):
    return import_service.create_batch(
        db, payload.exam_id, payload.import_type, payload.source, current_user.id
    )


@router.get("/batches", response_model=List[ImportBatchOut])
def list_batches(
    exam_id: Optional[UUID] = Query(default=None),
    batch_status: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:list")),
):
    query = db.query(ImportBatch)
    if exam_id:
        query = query.filter(ImportBatch.exam_id == exam_id)
    if batch_status:
        query = query.filter(ImportBatch.status == batch_status)
    return query.order_by(ImportBatch.created_at.desc()).all()


@router.get("/batches/{batch_id}", response_model=ImportBatchOut)
def get_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:view")),
):
    return import_service.get_batch_or_404(db, batch_id)


@router.post("/batches/{batch_id}/files", response_model=ImportUploadResult)
def upload_files(
    batch_id: UUID,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    auto_process: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:create")),
):
    batch = import_service.get_batch_or_404(db, batch_id)
    if batch.status == "processing":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="批次正在处理中，请稍后再试")

    pages = import_service.save_files(db, batch, files)
    if not pages:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未接收到有效的 PDF/图片文件")

    mode = "none"
    if auto_process:
        mode = dispatch_process_batch(batch.id, background_tasks)
    return ImportUploadResult(
        batch=ImportBatchOut.model_validate(batch),
        pages=[_page_out(db, p) for p in pages],
        mode=mode,
    )


@router.get("/batches/{batch_id}/progress", response_model=ImportProgressOut)
def get_progress(
    batch_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:view")),
):
    batch = import_service.get_batch_or_404(db, batch_id)
    return import_service.get_progress(db, batch)


@router.post("/batches/{batch_id}/process", response_model=ImportProgressOut)
def process_batch(
    batch_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:process")),
):
    batch = import_service.get_batch_or_404(db, batch_id)
    dispatch_process_batch(batch.id, background_tasks)
    db.refresh(batch)
    return import_service.get_progress(db, batch)


@router.get("/batches/{batch_id}/pages", response_model=List[ImportedPageOut])
def list_batch_pages(
    batch_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:view")),
):
    import_service.get_batch_or_404(db, batch_id)
    pages = (
        db.query(ImportedPage)
        .filter(ImportedPage.batch_id == batch_id)
        .order_by(ImportedPage.created_at, ImportedPage.original_page_index)
        .all()
    )
    return [_page_out(db, p) for p in pages]


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:delete")),
):
    batch = import_service.get_batch_or_404(db, batch_id)
    page_ids = [p.id for p in db.query(ImportedPage).filter(ImportedPage.batch_id == batch_id).all()]
    if page_ids:
        db.query(AnswerBlock).filter(AnswerBlock.page_id.in_(page_ids)).delete(synchronize_session=False)
        db.query(ExamException).filter(ExamException.page_id.in_(page_ids)).delete(synchronize_session=False)
        db.query(ImportedPage).filter(ImportedPage.batch_id == batch_id).delete(synchronize_session=False)
    import_service.delete_batch_files(batch)
    db.delete(batch)
    db.commit()
    return None


# ---------------- 答卷页与题块 ----------------

@router.get("/pages", response_model=List[ImportedPageOut])
def list_pages(
    exam_id: UUID = Query(...),
    batch_id: Optional[UUID] = Query(default=None),
    page_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:view")),
):
    query = db.query(ImportedPage).filter(ImportedPage.exam_id == exam_id)
    if batch_id:
        query = query.filter(ImportedPage.batch_id == batch_id)
    if page_status:
        query = query.filter(ImportedPage.status == page_status)
    pages = query.order_by(ImportedPage.created_at).offset(offset).limit(limit).all()
    return [_page_out(db, p) for p in pages]


def _page_or_404(db: Session, page_id: UUID) -> ImportedPage:
    page = db.query(ImportedPage).filter(ImportedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="答卷页不存在")
    return page


@router.get("/pages/{page_id}", response_model=ImportedPageOut)
def get_page(
    page_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:view")),
):
    return _page_out(db, _page_or_404(db, page_id))


@router.get("/pages/{page_id}/image")
def get_page_image(
    page_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("page:preview")),
):
    page = _page_or_404(db, page_id)
    if not page.preprocessed_image_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该页尚未生成预处理图像")
    return _file_response(page.preprocessed_image_path)


@router.get("/pages/{page_id}/original")
def get_page_original(
    page_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("page:preview")),
):
    page = _page_or_404(db, page_id)
    return _file_response(page.original_file_path)


@router.get("/pages/{page_id}/blocks", response_model=List[AnswerBlockOut])
def list_page_blocks(
    page_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("import:view")),
):
    _page_or_404(db, page_id)
    return (
        db.query(AnswerBlock)
        .filter(AnswerBlock.page_id == page_id)
        .order_by(AnswerBlock.y, AnswerBlock.x)
        .all()
    )


@router.post("/pages/{page_id}/exam-number", response_model=ImportedPageOut)
def set_exam_number(
    page_id: UUID,
    payload: ManualExamNumberIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("exam_number:manual")),
):
    page = import_service.set_page_exam_number(db, page_id, payload.exam_number.strip(), current_user.id)
    return _page_out(db, page)


@router.post("/pages/{page_id}/recut", response_model=ImportedPageOut)
def recut_page(
    page_id: UUID,
    payload: RecutIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("block:recut")),
):
    page = import_service.recut_page(
        db, page_id, current_user.id, perspective_points=payload.perspective_points
    )
    return _page_out(db, page)


@router.get("/blocks/{block_id}/image")
def get_block_image(
    block_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("page:preview")),
):
    block = db.query(AnswerBlock).filter(AnswerBlock.id == block_id).first()
    if not block or not block.image_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题块图像不存在")
    return _file_response(block.image_path)


# ---------------- 异常中心 ----------------

@router.get("/exceptions/summary")
def exception_summary(
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("exception:list")),
):
    rows = (
        db.query(ExamException.exception_type, ExamException.status, func.count(ExamException.id))
        .filter(ExamException.exam_id == exam_id)
        .group_by(ExamException.exception_type, ExamException.status)
        .all()
    )
    by_type: dict = {}
    by_status: dict = {"pending": 0, "resolved": 0, "ignored": 0}
    for exc_type, exc_status, count in rows:
        by_type.setdefault(exc_type, {"pending": 0, "resolved": 0, "ignored": 0})
        by_type[exc_type][exc_status] = count
        by_status[exc_status] = by_status.get(exc_status, 0) + count
    total = sum(by_status.values())
    return {"exam_id": exam_id, "total": total, "by_status": by_status, "by_type": by_type}


@router.get("/exceptions", response_model=List[ExceptionOut])
def list_exceptions(
    exam_id: UUID = Query(...),
    exc_status: Optional[str] = Query(default=None, alias="status"),
    exception_type: Optional[str] = Query(default=None),
    batch_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("exception:list")),
):
    query = db.query(ExamException).filter(ExamException.exam_id == exam_id)
    if exc_status:
        query = query.filter(ExamException.status == exc_status)
    if exception_type:
        query = query.filter(ExamException.exception_type == exception_type)
    if batch_id:
        query = query.join(ImportedPage, ExamException.page_id == ImportedPage.id).filter(
            ImportedPage.batch_id == batch_id
        )
    rows = query.order_by(ExamException.created_at.desc()).offset(offset).limit(limit).all()
    return [_exception_out(db, e) for e in rows]


@router.put("/exceptions/{exception_id}", response_model=ExceptionOut)
def update_exception(
    exception_id: UUID,
    payload: ExceptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("exception:resolve")),
):
    exc = db.query(ExamException).filter(ExamException.id == exception_id).first()
    if not exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异常记录不存在")

    exc.status = payload.status
    exc.resolution_action = payload.resolution_action
    exc.resolution_note = payload.resolution_note
    if payload.status in ("resolved", "ignored"):
        exc.resolved_by = current_user.id
        exc.resolved_at = datetime.now(timezone.utc)

    # 异常关闭后同步页状态
    if payload.status in ("resolved", "ignored") and exc.page_id:
        page = db.query(ImportedPage).filter(ImportedPage.id == exc.page_id).first()
        if page:
            remaining = db.query(ExamException).filter(
                ExamException.page_id == page.id,
                ExamException.status == "pending",
                ExamException.id != exc.id,
            ).count()
            if remaining == 0:
                page.status = "processed" if page.student_id else "matched"

    db.commit()
    db.refresh(exc)
    return _exception_out(db, exc)


@router.get("/exceptions/{exception_id}/snapshot")
def get_exception_snapshot(
    exception_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("exception:view")),
):
    exc = db.query(ExamException).filter(ExamException.id == exception_id).first()
    if not exc or not exc.snapshot_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异常快照不存在")
    return _file_response(exc.snapshot_path)


# ---------------- helpers ----------------

def _page_out(db: Session, page: ImportedPage) -> ImportedPageOut:
    out = ImportedPageOut.model_validate(page)
    if page.student_id:
        student = db.query(Student).filter(Student.id == page.student_id).first()
        if student:
            out.student_name = student.name
            out.class_name = student.class_name
    return out


def _exception_out(db: Session, exc: ExamException) -> ExceptionOut:
    out = ExceptionOut.model_validate(exc)
    if exc.page_id:
        page = db.query(ImportedPage).filter(ImportedPage.id == exc.page_id).first()
        if page:
            out.exam_number_ocr = page.exam_number_ocr
            if page.student_id:
                student = db.query(Student).filter(Student.id == page.student_id).first()
                if student:
                    out.student_name = student.name
    return out


def _file_response(relative_path: str) -> FileResponse:
    full_path = absolute_path(relative_path)
    if not full_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return FileResponse(path=str(full_path))