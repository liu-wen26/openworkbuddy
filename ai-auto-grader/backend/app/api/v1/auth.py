from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.core.security import verify_password, create_access_token, get_current_user_id
from app.models.user import User
from app.schemas.user import UserLogin, Token, UserOut
from app.services import audit_service

router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer()


@router.post("/login", response_model=Token)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        # 失败登录记录尝试的用户名与来源 IP，便于安全审计检索（MID-3）
        audit_service.record_action(
            db, None, "login_failed", "auth",
            {"username": payload.username, "ip": ip, "reason": "invalid_credentials"},
            username=payload.username,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        audit_service.record_action(
            db, user, "login_failed", "auth",
            {"username": user.username, "ip": ip, "reason": "inactive"},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
    token = create_access_token(subject=str(user.id))
    # 登录成功回填用户身份，使审计可按用户检索（MID-3）
    audit_service.record_action(
        db, user, "login", "auth",
        {"username": user.username, "ip": ip},
    )
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
