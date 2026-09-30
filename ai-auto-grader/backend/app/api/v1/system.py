"""系统设置与运维 API（F9、F11 系列）。"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import get_current_user_id
from app.db.base import get_db
from app.models.user import User
from app.services import audit_service, monitor_service, settings_service
from app.services.ai_service import check_llm_connection

router = APIRouter(prefix="/system", tags=["系统设置"])


def _current_user(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
    return user


# ---------------- F11-01 大模型配置 ----------------

class LLMConfigIn(BaseModel):
    provider: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    confidence_threshold: Optional[float] = None
    enabled: Optional[bool] = None


class WatermarkIn(BaseModel):
    enabled: Optional[bool] = None
    text: Optional[str] = None
    opacity: Optional[float] = None
    color: Optional[str] = None
    font_size: Optional[int] = None
    rotate: Optional[int] = None
    position: Optional[str] = None


class NotificationIn(BaseModel):
    enabled: Optional[bool] = None
    channels: Optional[List[str]] = None
    events: Optional[List[str]] = None
    recipients: Optional[List[str]] = None


class PreferencesIn(BaseModel):
    default_zoom: Optional[float] = None
    image_fit: Optional[str] = None
    keyboard_shortcuts: Optional[bool] = None
    auto_next: Optional[bool] = None
    show_ai_comment: Optional[bool] = None
    score_step: Optional[float] = None


class RolePermissionsIn(BaseModel):
    permissions: List[str]


@router.get("/llm-config")
def get_llm_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:view")),
):
    return settings_service.mask_llm_config(settings_service.get_llm_config(db))


@router.put("/llm-config")
def update_llm_config(
    payload: LLMConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:manage")),
):
    config = settings_service.set_llm_config(db, payload.model_dump(exclude_unset=True), current_user.id)
    audit_service.record_action(
        db, current_user, "system_update", "system",
        {"target": "llm_config", "provider": config.get("provider"), "model": config.get("model")},
    )
    return settings_service.mask_llm_config(config)


@router.post("/llm-config/test")
def test_llm_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:manage")),
):
    config = settings_service.get_llm_config(db)
    result = check_llm_connection(config)
    audit_service.record_action(db, current_user, "system_test", "system", {"target": "llm_config", **result})
    return result


# ---------------- F11-03 水印 ----------------

@router.get("/watermark")
def get_watermark(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:view")),
):
    return settings_service.get_watermark(db)


@router.get("/watermark/public")
def get_watermark_public(
    db: Session = Depends(get_db),
    current_user: User = Depends(_current_user),
):
    """供前端布局渲染水印叠加层（不含敏感信息）。"""
    return settings_service.get_watermark(db)


@router.put("/watermark")
def update_watermark(
    payload: WatermarkIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:manage")),
):
    result = settings_service.set_watermark(db, payload.model_dump(exclude_unset=True), current_user.id)
    audit_service.record_action(db, current_user, "system_update", "system",
                                {"target": "watermark", "enabled": result.get("enabled")})
    return result


# ---------------- F11-04 消息通知 ----------------

@router.get("/notification")
def get_notification(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:view")),
):
    return {
        "config": settings_service.get_notification(db),
        "events": settings_service.NOTIFICATION_EVENTS,
    }


@router.put("/notification")
def update_notification(
    payload: NotificationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:manage")),
):
    result = settings_service.set_notification(db, payload.model_dump(exclude_unset=True), current_user.id)
    audit_service.record_action(db, current_user, "system_update", "system",
                                {"target": "notification", "enabled": result.get("enabled")})
    return result


# ---------------- F11-02 阅卷界面偏好 ----------------

@router.get("/preferences")
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(_current_user),
):
    return settings_service.get_preferences(db, current_user.id)


@router.put("/preferences")
def update_preferences(
    payload: PreferencesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_current_user),
):
    return settings_service.set_preferences(db, current_user.id, payload.model_dump(exclude_unset=True))


# ---------------- F9-01 角色权限 ----------------

@router.get("/roles")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:view")),
):
    return {
        "roles": settings_service.list_roles(db),
        "catalog": settings_service.PERMISSION_CATALOG,
    }


@router.put("/roles/{role}")
def update_role_permissions(
    role: str,
    payload: RolePermissionsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("role:manage")),
):
    try:
        result = settings_service.set_role_permissions(db, role, payload.permissions, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit_service.record_action(db, current_user, "role_update", "system",
                                {"role": role, "permission_count": len(result["permissions"])})
    return result


# ---------------- F9-02 阅卷进度监控 ----------------

@router.get("/monitor/exams")
def monitor_exams(
    exam_status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("monitor:view")),
):
    return monitor_service.list_exam_progress(db, exam_status)


@router.get("/monitor/exams/{exam_id}")
def monitor_exam_detail(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("monitor:view")),
):
    return monitor_service.exam_progress(db, exam_id)


# ---------------- F9-03 审计日志 ----------------

@router.get("/audit-logs")
def list_audit_logs(
    user_id: Optional[UUID] = None,
    role: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    path: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:view")),
):
    logs = audit_service.list_logs(
        db, user_id=user_id, role=role, action=action, resource_type=resource_type,
        path=path, start=start, end=end, limit=limit, offset=offset,
    )
    return {
        "total": audit_service.count_logs(db, action=action, resource_type=resource_type),
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": log.username,
                "role": log.role,
                "action": log.action,
                "method": log.method,
                "path": log.path,
                "resource_type": log.resource_type,
                "status_code": log.status_code,
                "ip": log.ip,
                "detail": log.detail,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    }