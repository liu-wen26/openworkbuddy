"""操作审计日志服务（F9-03）。

两种写入方式：
  - 自动：中间件对 /api/v1 下的写操作（POST/PUT/PATCH/DELETE）统一落一条日志；
  - 显式：导出、归档、权限变更等关键动作调用 record_action 补充业务语义。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)

METHOD_ACTION = {
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}

# 路径片段 -> 资源类型
RESOURCE_HINTS = [
    ("exams", "exam"), ("templates", "template"), ("imports", "import"),
    ("choices", "choice"), ("grading", "grading"), ("precheck", "precheck"),
    ("analytics", "analytics"), ("exports", "export"), ("archives", "archive"),
    ("system", "system"), ("users", "user"), ("auth", "auth"), ("scoring", "grading"),
]


def _resource_type(path: str) -> Optional[str]:
    for fragment, name in RESOURCE_HINTS:
        if f"/{fragment}" in path:
            return name
    return None


def record(
    db: Session,
    *,
    action: str,
    user: Optional[User] = None,
    username: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    resource_type: Optional[str] = None,
    status_code: Optional[int] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else username,
        role=user.role if user else None,
        action=action,
        method=method,
        path=path,
        resource_type=resource_type or (_resource_type(path) if path else None),
        status_code=status_code,
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
        detail=detail,
    )
    db.add(log)
    return log


def record_action(
    db: Session,
    user: Optional[User],
    action: str,
    resource_type: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
    commit: bool = True,
    username: Optional[str] = None,
) -> None:
    """登记关键业务动作（导出/归档/权限变更/登录等）。

    无 user 对象时（如登录失败）可通过 username 记录尝试的用户名。
    """
    try:
        record(db, action=action, user=user, username=username, resource_type=resource_type, detail=detail)
        if commit:
            db.commit()
    except Exception as exc:  # noqa: BLE001  审计失败不应阻断主流程
        logger.warning("审计日志写入失败: %s", exc)
        db.rollback()


def record_request(
    *,
    method: str,
    path: str,
    status_code: int,
    ip: Optional[str],
    user_agent: Optional[str],
    user_id: Optional[str] = None,
) -> None:
    """供中间件调用，使用独立会话，避免影响请求事务。"""
    if method not in METHOD_ACTION:
        return
    if status_code >= 400:
        # 失败请求也记录，action 标记为 failed
        action = f"{METHOD_ACTION[method]}_failed"
    else:
        action = METHOD_ACTION[method]
    session = SessionLocal()
    try:
        user = None
        if user_id:
            try:
                user = session.query(User).filter(User.id == UUID(str(user_id))).first()
            except (ValueError, TypeError):
                user = None
        record(
            session,
            action=action,
            user=user,
            method=method,
            path=path,
            status_code=status_code,
            ip=ip,
            user_agent=user_agent,
            detail={"timestamp": datetime.now(timezone.utc).isoformat()},
        )
        session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("请求审计日志写入失败: %s", exc)
        session.rollback()
    finally:
        session.close()


def list_logs(
    db: Session,
    *,
    user_id: Optional[UUID] = None,
    role: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    path: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[AuditLog]:
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if role:
        query = query.filter(AuditLog.role == role)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if path:
        query = query.filter(AuditLog.path.ilike(f"%{path}%"))
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)
    return (
        query.order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(min(limit, 500))
        .all()
    )


def count_logs(
    db: Session,
    *,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
) -> int:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    return query.count()