from typing import List

from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.core.security import get_current_user_id
from app.models.user import User


ROLE_PERMISSIONS = {
    "super_admin": ["*"],
    "exam_admin": [
        "exam:create", "exam:update", "exam:delete", "exam:list", "exam:view",
        "paper:upload", "paper:replace", "paper:delete", "paper:view",
        "template:create", "template:update", "template:delete", "template:list",
        "student:import", "student:manage",
        "import:create", "import:list", "import:delete", "import:process", "import:view",
        "exception:list", "exception:view", "exception:resolve", "exception:ignore",
        "page:preview", "block:recut", "exam_number:manual",
        "choice:grade", "choice:review", "choice:view",
        "scoring:grade", "scoring:ai", "scoring:distribute", "scoring:arbitrate",
        "scoring:view_all", "scoring:log",
        "analytics:view", "export:download", "archive:create",
        "precheck:view", "precheck:upload", "precheck:run", "precheck:clear",
        "user:list", "user:view", "user:create",
    ],
    "group_leader": [
        "exam:list", "exam:view",
        "paper:view",
        "import:list", "import:view",
        "scoring:distribute", "scoring:arbitrate",
        "scoring:grade", "scoring:ai", "scoring:view_all", "scoring:log",
        "exception:list", "exception:view", "exception:resolve", "exception:ignore",
        "page:preview", "block:recut", "exam_number:manual",
        "choice:grade", "choice:review", "choice:view",
        "analytics:view", "export:download",
        "precheck:view", "precheck:upload", "precheck:run", "precheck:clear",
    ],
    "teacher": [
        "exam:list", "exam:view",
        "paper:view",
        "scoring:grade", "scoring:view_own",
        "choice:view",
        "analytics:view_limited",
    ],
}


def has_permission(user_role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(user_role, [])
    if "*" in perms:
        return True
    return permission in perms


def require_permission(permission: str):
    def checker(
        user_id: str = Depends(get_current_user_id),
        db: Session = Depends(get_db),
    ) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
        if not has_permission(user.role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user
    return checker


def require_roles(roles: List[str]):
    def checker(
        user_id: str = Depends(get_current_user_id),
        db: Session = Depends(get_db),
    ) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active or user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user
    return checker
