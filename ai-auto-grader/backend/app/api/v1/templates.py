from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.core.permissions import require_permission
from app.models.user import User
from app.models.template import AnswerCardTemplate

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get("")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    return db.query(AnswerCardTemplate).order_by(AnswerCardTemplate.created_at.desc()).all()


@router.get("/{template_id}")
def get_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    tpl = db.query(AnswerCardTemplate).filter(AnswerCardTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return tpl
