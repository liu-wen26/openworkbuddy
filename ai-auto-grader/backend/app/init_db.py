import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import Base, engine, SessionLocal
from app.models.user import User
from app.core.security import get_password_hash


def init():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        default_users = [
            ("admin", "超级管理员", "super_admin", "admin123"),
            ("jiaowu", "教务管理员", "exam_admin", "jiaowu123"),
            ("jiaoyan", "教研组长", "group_leader", "jiaoyan123"),
            ("teacher", "阅卷教师", "teacher", "teacher123"),
        ]
        for username, real_name, role, password in default_users:
            exists = db.query(User).filter(User.username == username).first()
            if not exists:
                user = User(
                    username=username,
                    real_name=real_name,
                    password_hash=get_password_hash(password),
                    role=role,
                )
                db.add(user)
        db.commit()
        print("Database initialized with default users.")
    finally:
        db.close()


if __name__ == "__main__":
    init()
