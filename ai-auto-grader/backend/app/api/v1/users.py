from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.core.security import get_password_hash
from app.core.permissions import ROLE_PERMISSIONS, require_permission
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import audit_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("", response_model=UserOut)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:create")),
):
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
    db_user = User(
        username=payload.username,
        real_name=payload.real_name,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        email=payload.email,
        phone=payload.phone,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    audit_service.record_action(
        db, current_user, "create", "user",
        {"username": db_user.username, "role": db_user.role},
    )
    return db_user


@router.get("", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:list")),
):
    return db.query(User).all()


@router.get("/roles")
def list_roles(
    current_user: User = Depends(require_permission("user:view")),
):
    """可分配角色清单（F9-01 角色分配用）。"""
    labels = {
        "super_admin": "超级管理员",
        "exam_admin": "教务管理员",
        "group_leader": "教研组长",
        "teacher": "阅卷教师",
    }
    return [{"role": role, "label": labels.get(role, role)} for role in ROLE_PERMISSIONS.keys()]


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:update")),
):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    data = payload.model_dump(exclude_unset=True)
    if "role" in data and data["role"] not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未知角色")
    if "password" in data:
        db_user.password_hash = get_password_hash(data.pop("password"))
    for field, value in data.items():
        setattr(db_user, field, value)
    db.commit()
    db.refresh(db_user)
    audit_service.record_action(
        db, current_user, "update", "user",
        {"username": db_user.username, "role": db_user.role, "is_active": db_user.is_active,
         "changed": list(payload.model_dump(exclude_unset=True).keys())},
    )
    return db_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:update")),
):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if db_user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录用户")
    username = db_user.username
    db.delete(db_user)
    db.commit()
    audit_service.record_action(db, current_user, "delete", "user", {"username": username})
    return None


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:view")),
):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user
