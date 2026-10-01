"""站内消息通知 API（F11-04）。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db.base import get_db
from app.models.notification import Notification
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["通知"])


def _current_user_id(user_id: str = Depends(get_current_user_id)) -> UUID:
    return UUID(str(user_id))


def _serialize(row: Notification) -> dict:
    return {
        "id": row.id,
        "event": row.event,
        "title": row.title,
        "content": row.content,
        "level": row.level,
        "link": row.link,
        "meta": row.meta,
        "is_read": row.is_read,
        "created_at": row.created_at,
        "read_at": row.read_at,
    }


@router.get("")
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(_current_user_id),
):
    items = notification_service.list_for_user(
        db, user_id, unread_only=unread_only, limit=limit, offset=offset
    )
    return {
        "total": notification_service.count_for_user(db, user_id),
        "unread": notification_service.count_for_user(db, user_id, unread_only=True),
        "items": [_serialize(row) for row in items],
    }


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(_current_user_id),
):
    return {"unread": notification_service.count_for_user(db, user_id, unread_only=True)}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(_current_user_id),
):
    row = notification_service.mark_read(db, user_id, notification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")
    return _serialize(row)


@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(_current_user_id),
):
    return {"updated": notification_service.mark_all_read(db, user_id)}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(_current_user_id),
):
    if not notification_service.delete(db, user_id, notification_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")
    return None