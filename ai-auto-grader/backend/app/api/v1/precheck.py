"""预阅卷预览 API（F5 系列）。

在正式导入前用少量样卷（≤20 份）试跑「预处理 → 考号识别 → 题块切割 →
选择题 OMR → 非选择题 AI 预评」整条链路，验证模板与 AI 效果。
数据写入独立的 precheck_sessions / precheck_pages，与正式数据完全隔离。
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.db.base import get_db
from app.models.user import User
from app.schemas.precheck import (
    PrecheckClearOut,
    PrecheckSessionCreate,
    PrecheckSessionDetailOut,
    PrecheckSessionOut,
    PrecheckUploadResult,
)
from app.services import precheck_service
from app.tasks.precheck_tasks import dispatch_precheck
from app.utils.file_storage import absolute_path

router = APIRouter(prefix="/precheck", tags=["预阅卷预览"])


@router.post("/sessions", response_model=PrecheckSessionOut)
def open_session(
    payload: PrecheckSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("precheck:run")),
):
    """打开（或复用）该考试的活跃预阅卷会话。"""
    return precheck_service.open_session(db, payload.exam_id, current_user.id)


@router.get("/sessions", response_model=List[PrecheckSessionOut])
def list_sessions(
    exam_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("precheck:view")),
):
    return precheck_service.list_sessions(db, exam_id)


@router.get("/sessions/{session_id}", response_model=PrecheckSessionDetailOut)
def get_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("precheck:view")),
):
    session = precheck_service.get_session_or_404(db, session_id)
    detail = precheck_service.build_detail(db, session)
    out = PrecheckSessionDetailOut.model_validate(session)
    out.pages = detail["pages"]
    return out


@router.post("/sessions/{session_id}/samples", response_model=PrecheckUploadResult)
def upload_samples(
    session_id: UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("precheck:upload")),
):
    """上传样卷（PDF 或图片），最多 20 份。"""
    session = precheck_service.get_session_or_404(db, session_id)
    added, pages = precheck_service.save_samples(db, session, files)
    return PrecheckUploadResult(
        session=PrecheckSessionOut.model_validate(session),
        added=added,
        pages=pages,
    )


@router.post("/sessions/{session_id}/run", response_model=PrecheckSessionOut)
def run_session(
    session_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("precheck:run")),
):
    """执行预阅卷流水线（异步，前端轮询详情获取进度）。"""
    session = precheck_service.get_session_or_404(db, session_id)
    if session.status not in precheck_service.RUNNABLE_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该会话正在执行或已清空，请稍后再试")
    dispatch_precheck(session.id, background_tasks)
    db.refresh(session)
    return session


@router.post("/sessions/{session_id}/clear", response_model=PrecheckClearOut)
def clear_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("precheck:clear")),
):
    """清空预阅卷数据：删除全部样卷页记录与临时文件。"""
    session = precheck_service.get_session_or_404(db, session_id)
    return precheck_service.clear_session(db, session)


# ---------------- 样卷页图像 ----------------

@router.get("/pages/{page_id}/image")
def get_page_image(
    page_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("precheck:view")),
):
    page = precheck_service.get_page_or_404(db, page_id)
    if not page.preprocessed_image_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该页尚未生成预处理图像")
    return _file_response(page.preprocessed_image_path)


@router.get("/pages/{page_id}/blocks/{block_index}/image")
def get_block_image(
    page_id: UUID,
    block_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("precheck:view")),
):
    return _file_response(precheck_service.get_block_image_path(db, page_id, block_index))


def _file_response(relative_path: str) -> FileResponse:
    full_path = absolute_path(relative_path)
    if not full_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return FileResponse(path=str(full_path))