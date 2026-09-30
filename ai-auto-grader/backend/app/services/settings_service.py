"""系统设置服务（F11）：大模型配置、水印、消息通知、阅卷界面偏好，以及角色权限覆盖（F9-01）。

所有配置以 JSON 形式落在 system_settings 键值表；未配置的键回落到代码内默认值，
保证系统在未做任何设置时也能正常运行。
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.permissions import ROLE_PERMISSIONS
from app.db.base import SessionLocal
from app.models.system_setting import RolePermission, SystemSetting

logger = logging.getLogger(__name__)

KEY_LLM = "llm_config"
KEY_WATERMARK = "watermark"
KEY_NOTIFICATION = "notification"
KEY_USER_PREF_PREFIX = "user_pref:"

LLM_DEFAULT: Dict[str, Any] = {
    "provider": "openai",          # openai / local / mock
    "api_base": None,
    "api_key": "",
    "model": "gpt-4o",
    "confidence_threshold": 0.7,
    "enabled": True,
}

WATERMARK_DEFAULT: Dict[str, Any] = {
    "enabled": False,
    "text": "AI自动阅卷系统 机密",
    "opacity": 0.12,
    "color": "#909399",
    "font_size": 16,
    "rotate": -25,
    "position": "center",          # center / tile
}

NOTIFICATION_DEFAULT: Dict[str, Any] = {
    "enabled": True,
    "channels": ["in_app"],        # in_app / email
    "events": [
        "grading_assigned",
        "grading_completed",
        "arbitration_required",
        "import_finished",
        "exception_created",
    ],
    "recipients": [],
}

PREFERENCE_DEFAULT: Dict[str, Any] = {
    "default_zoom": 1.0,
    "image_fit": "width",          # width / height / contain
    "keyboard_shortcuts": True,
    "auto_next": True,
    "show_ai_comment": True,
    "score_step": 0.5,
}

NOTIFICATION_EVENTS = [
    {"key": "grading_assigned", "label": "阅卷任务分配"},
    {"key": "grading_completed", "label": "阅卷完成"},
    {"key": "arbitration_required", "label": "需仲裁"},
    {"key": "import_finished", "label": "答卷导入完成"},
    {"key": "exception_created", "label": "新增异常"},
]

# 可在前端展示的权限清单（用于角色权限编辑器分组）
PERMISSION_CATALOG = [
    {"group": "考试与试卷", "items": [
        ("exam:create", "创建考试"), ("exam:update", "编辑考试"), ("exam:delete", "删除考试"),
        ("exam:list", "查看考试列表"), ("exam:view", "查看考试详情"),
        ("paper:upload", "上传原试卷"), ("paper:replace", "替换原试卷"),
        ("paper:delete", "删除原试卷"), ("paper:view", "查看原试卷"),
        ("student:import", "导入考生"), ("student:manage", "管理考生"),
    ]},
    {"group": "答题卡模板", "items": [
        ("template:create", "创建模板"), ("template:update", "编辑模板"),
        ("template:delete", "删除模板"), ("template:list", "查看模板列表"),
    ]},
    {"group": "答卷导入与切割", "items": [
        ("import:create", "创建导入批次"), ("import:list", "查看批次"), ("import:view", "查看答卷页"),
        ("import:process", "执行导入处理"), ("import:delete", "删除批次"),
        ("exception:list", "查看异常列表"), ("exception:view", "查看异常详情"),
        ("exception:resolve", "处理异常"), ("exception:ignore", "忽略异常"),
        ("page:preview", "预览答卷页"), ("block:recut", "重切题块"), ("exam_number:manual", "手动指定考号"),
    ]},
    {"group": "选择题判分", "items": [
        ("choice:grade", "选择题判分"), ("choice:review", "选择题异常复核"), ("choice:view", "查看选择题结果"),
    ]},
    {"group": "非选择题阅卷", "items": [
        ("scoring:grade", "人工评分"), ("scoring:ai", "AI 预评"), ("scoring:distribute", "分发阅卷任务"),
        ("scoring:arbitrate", "仲裁"), ("scoring:view_all", "查看全部阅卷"), ("scoring:view_own", "查看本人阅卷"),
        ("scoring:log", "查看阅卷痕迹"),
    ]},
    {"group": "预阅卷", "items": [
        ("precheck:view", "查看预阅卷"), ("precheck:upload", "上传样卷"),
        ("precheck:run", "执行预阅卷"), ("precheck:clear", "清空预阅卷"),
    ]},
    {"group": "学情与导出", "items": [
        ("analytics:view", "查看学情分析"), ("analytics:view_limited", "查看受限学情"),
        ("export:download", "导出成绩/答卷"), ("archive:create", "归档考试"),
        ("archive:view", "查看归档"), ("archive:delete", "删除归档"),
    ]},
    {"group": "系统管理", "items": [
        ("monitor:view", "阅卷进度监控"), ("audit:view", "查看审计日志"),
        ("user:list", "查看用户"), ("user:view", "查看用户详情"),
        ("user:create", "创建用户"), ("user:update", "编辑用户"),
        ("role:manage", "角色权限管理"), ("system:view", "查看系统设置"), ("system:manage", "修改系统设置"),
    ]},
]


# ---------------- 通用键值读写 ----------------

def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row or row.value is None:
        return default
    return row.value


def set_setting(db: Session, key: str, value: Any, user_id: Optional[UUID] = None) -> Any:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row is None:
        row = SystemSetting(key=key, value=value, updated_by=user_id)
        db.add(row)
    else:
        row.value = value
        row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row.value


def _merge(default: Dict[str, Any], stored: Any) -> Dict[str, Any]:
    merged = dict(default)
    if isinstance(stored, dict):
        merged.update(stored)
    return merged


# ---------------- 大模型配置（F11-01） ----------------

def get_llm_config(db: Optional[Session] = None) -> Dict[str, Any]:
    own = db is None
    session = db or SessionLocal()
    try:
        return _merge(LLM_DEFAULT, get_setting(session, KEY_LLM))
    finally:
        if own:
            session.close()


def set_llm_config(db: Session, value: Dict[str, Any], user_id: Optional[UUID]) -> Dict[str, Any]:
    current = get_llm_config(db)
    stored = get_setting(db, KEY_LLM, {}) or {}
    merged = {**current, **{k: v for k, v in value.items() if v is not None}}
    # 前端回显的掩码 key 不覆盖真实 key
    if merged.get("api_key") == "******":
        merged["api_key"] = stored.get("api_key", "")
    set_setting(db, KEY_LLM, merged, user_id)
    return merged


def mask_llm_config(config: Dict[str, Any]) -> Dict[str, Any]:
    masked = dict(config)
    if masked.get("api_key"):
        masked["api_key"] = "******"
    return masked


# ---------------- 水印（F11-03） ----------------

def get_watermark(db: Optional[Session] = None) -> Dict[str, Any]:
    own = db is None
    session = db or SessionLocal()
    try:
        return _merge(WATERMARK_DEFAULT, get_setting(session, KEY_WATERMARK))
    finally:
        if own:
            session.close()


def set_watermark(db: Session, value: Dict[str, Any], user_id: Optional[UUID]) -> Dict[str, Any]:
    merged = {**get_watermark(db), **{k: v for k, v in value.items() if v is not None}}
    set_setting(db, KEY_WATERMARK, merged, user_id)
    return merged


# ---------------- 消息通知（F11-04） ----------------

def get_notification(db: Optional[Session] = None) -> Dict[str, Any]:
    own = db is None
    session = db or SessionLocal()
    try:
        return _merge(NOTIFICATION_DEFAULT, get_setting(session, KEY_NOTIFICATION))
    finally:
        if own:
            session.close()


def set_notification(db: Session, value: Dict[str, Any], user_id: Optional[UUID]) -> Dict[str, Any]:
    updates = {k: v for k, v in value.items() if v is not None}
    current = get_notification(db)
    # 事件订阅采用「默认 ∪ 已存 ∪ 传入」并集：避免部分更新把默认订阅整表覆盖/清空，
    # 导致通知闭环被静默关闭（HIGH-2）。
    incoming = updates.pop("events", None)
    events: List[str] = []
    for source in (NOTIFICATION_DEFAULT["events"], current.get("events"), incoming):
        for event in source or []:
            if event not in events:
                events.append(event)
    merged = {**current, **updates, "events": events}
    set_setting(db, KEY_NOTIFICATION, merged, user_id)
    return merged


# ---------------- 阅卷界面偏好（F11-02，按用户） ----------------

def get_preferences(db: Session, user_id: UUID) -> Dict[str, Any]:
    return _merge(PREFERENCE_DEFAULT, get_setting(db, f"{KEY_USER_PREF_PREFIX}{user_id}"))


def set_preferences(db: Session, user_id: UUID, value: Dict[str, Any]) -> Dict[str, Any]:
    merged = {**get_preferences(db, user_id), **{k: v for k, v in value.items() if v is not None}}
    set_setting(db, f"{KEY_USER_PREF_PREFIX}{user_id}", merged, user_id)
    return merged


# ---------------- 角色权限（F9-01） ----------------

def role_overrides(db: Session) -> Dict[str, Dict[str, bool]]:
    overrides: Dict[str, Dict[str, bool]] = {}
    for row in db.query(RolePermission).all():
        overrides.setdefault(row.role, {})[row.permission] = bool(row.allowed)
    return overrides


def effective_permissions(role: str) -> List[str]:
    """返回角色最终权限清单（内置默认 + 数据库覆盖）。"""
    session = SessionLocal()
    try:
        base = ROLE_PERMISSIONS.get(role, [])
        if "*" in base:
            return ["*"]
        return _effective_from(base, role_overrides(session).get(role, {}))
    finally:
        session.close()


def has_permission_db(db: Session, role: str, permission: str) -> bool:
    base = ROLE_PERMISSIONS.get(role, [])
    if "*" in base:
        return True
    overrides = role_overrides(db).get(role, {})
    if permission in overrides:
        return overrides[permission]
    return permission in base


def _effective_from(base: List[str], overrides: Dict[str, bool]) -> List[str]:
    perms = set(base)
    for permission, allowed in overrides.items():
        if allowed:
            perms.add(permission)
        else:
            perms.discard(permission)
    return sorted(perms)


def list_roles(db: Session) -> List[dict]:
    overrides = role_overrides(db)
    roles = []
    for role in ROLE_PERMISSIONS.keys():
        base = ROLE_PERMISSIONS.get(role, [])
        is_super = "*" in base
        roles.append({
            "role": role,
            "is_super": is_super,
            "permissions": ["*"] if is_super else _effective_from(base, overrides.get(role, {})),
            "overrides": overrides.get(role, {}),
        })
    return roles


def set_role_permissions(db: Session, role: str, permissions: List[str], user_id: Optional[UUID]) -> dict:
    """把 permissions 作为该角色的最终权限集合，仅记录与内置默认的差异。"""
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"未知角色: {role}")
    base = set(ROLE_PERMISSIONS.get(role, []))
    if "*" in base:
        raise ValueError("超级管理员权限不可修改")

    target = set(permissions)
    db.query(RolePermission).filter(RolePermission.role == role).delete()
    for permission in target - base:            # 额外授予
        db.add(RolePermission(role=role, permission=permission, allowed=True, updated_by=user_id))
    for permission in base - target:            # 显式禁用
        db.add(RolePermission(role=role, permission=permission, allowed=False, updated_by=user_id))
    db.commit()
    return {"role": role, "permissions": sorted(target)}