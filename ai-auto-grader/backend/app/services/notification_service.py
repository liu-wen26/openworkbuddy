"""站内消息通知服务（F11-04 通知闭环）。

业务事件发生时由各服务调用 `emit_event`：
1. 读取系统设置中的通知配置（是否启用、渠道、订阅的事件）决定是否投递；
2. 为每位收件人写入一条站内消息，并实时推送到其个人 topic；
3. 邮件渠道在未配置 SMTP 时降级为日志占位，不影响主流程。

使用独立会话，避免影响调用方事务；任何异常都不阻断主业务。
"""

import logging
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.notification import Notification
from app.models.user import User
from app.services import realtime, settings_service

logger = logging.getLogger(__name__)

# 事件默认展示信息（可被调用方覆盖）
EVENT_DEFAULTS: Dict[str, Dict[str, str]] = {
    "grading_assigned": {"title": "新的阅卷任务", "level": "info"},
    "grading_completed": {"title": "阅卷已完成", "level": "success"},
    "arbitration_required": {"title": "有任务需要仲裁", "level": "warning"},
    "import_finished": {"title": "答卷导入完成", "level": "success"},
    "exception_created": {"title": "新增待处理异常", "level": "warning"},
}


def emit_event(
    event_key: str,
    *,
    content: str,
    title: Optional[str] = None,
    level: Optional[str] = None,
    link: Optional[str] = None,
    recipient_ids: Optional[Iterable[Any]] = None,
    recipient_roles: Optional[Iterable[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
    actor_id: Optional[Any] = None,
    db: Optional[Session] = None,
) -> int:
    """按配置投递一条业务通知，返回实际写入的消息条数。"""
    own = db is None
    session = db or SessionLocal()
    try:
        config = settings_service.get_notification(session)
        if not config.get("enabled", True):
            return 0
        if config.get("events") and event_key not in config["events"]:
            logger.debug("通知事件未订阅，跳过投递 event=%s（已订阅: %s）", event_key, config["events"])
            return 0

        recipients = _resolve_recipients(session, recipient_ids, recipient_roles, actor_id)
        if not recipients:
            return 0

        defaults = EVENT_DEFAULTS.get(event_key, {})
        final_title = title or defaults.get("title", event_key)
        final_level = level or defaults.get("level", "info")

        created = 0
        for user in recipients:
            row = Notification(
                user_id=user.id,
                event=event_key,
                title=final_title,
                content=content,
                level=final_level,
                link=link,
                actor_id=_as_uuid(actor_id),
                meta=meta,
            )
            session.add(row)
            session.flush()
            created += 1
            realtime.publish_user_event(
                user.id,
                "notification",
                {
                    "id": str(row.id),
                    "event": event_key,
                    "title": final_title,
                    "content": content,
                    "level": final_level,
                    "link": link,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                },
            )
        session.commit()

        if "email" in (config.get("channels") or []):
            _send_email_stub(config, recipients, final_title, content)
        return created
    except Exception as exc:  # noqa: BLE001  通知失败不应阻断主流程
        logger.warning("通知投递失败 event=%s: %s", event_key, exc)
        session.rollback()
        return 0
    finally:
        if own:
            session.close()


def _send_email_stub(config: Dict[str, Any], recipients: List[User], title: str, content: str) -> None:
    """邮件渠道占位实现：未接入 SMTP 时记录日志。

    config.recipients 中的附加邮箱也会被记录，便于后续接入真实邮件服务。
    """
    extra = config.get("recipients") or []
    addresses = [u.email for u in recipients if u.email] + [a for a in extra if a]
    if addresses:
        logger.info("邮件通知（占位，未发送）收件人=%s 主题=%s 内容=%s", addresses, title, content)


def _resolve_recipients(
    db: Session,
    recipient_ids: Optional[Iterable[Any]],
    recipient_roles: Optional[Iterable[str]],
    actor_id: Optional[Any],
) -> List[User]:
    wanted_ids = {_as_uuid(i) for i in (recipient_ids or []) if i}
    wanted_ids.discard(None)
    roles = list(recipient_roles or [])
    # 按角色投递的业务/监控通知同时纳入超级管理员，避免管理员看不到任何业务通知（HIGH-2）。
    # 定向分配（仅 recipient_ids）不在此列，仍只发给指定阅卷人。
    if roles and "super_admin" not in roles:
        roles.append("super_admin")

    query = db.query(User).filter(User.is_active.is_(True))
    users: List[User] = []
    if wanted_ids and roles:
        users = query.filter((User.id.in_(wanted_ids)) | (User.role.in_(roles))).all()
    elif wanted_ids:
        users = query.filter(User.id.in_(wanted_ids)).all()
    elif roles:
        users = query.filter(User.role.in_(roles)).all()

    actor = _as_uuid(actor_id)
    # 去重，且不给自己发通知
    unique: Dict[UUID, User] = {}
    for user in users:
        if actor and user.id == actor:
            continue
        unique[user.id] = user
    return list(unique.values())


def _as_uuid(value: Any) -> Optional[UUID]:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


# ---------------- 查询与已读 ----------------

def list_for_user(
    db: Session,
    user_id: UUID,
    *,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> List[Notification]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()


def count_for_user(db: Session, user_id: UUID, *, unread_only: bool = False) -> int:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.count()


def mark_read(db: Session, user_id: UUID, notification_id: UUID) -> Optional[Notification]:
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not row:
        return None
    if not row.is_read:
        row.is_read = True
        from datetime import datetime, timezone

        row.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


def mark_all_read(db: Session, user_id: UUID) -> int:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .update({Notification.is_read: True, Notification.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return int(count or 0)


def delete(db: Session, user_id: UUID, notification_id: UUID) -> bool:
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True