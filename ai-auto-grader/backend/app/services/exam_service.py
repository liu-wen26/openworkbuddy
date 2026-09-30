"""考试领域公共辅助。

`check_exam_modifiable` 统一了「锁定/归档后禁止写入」的口径，供考试更新、
花名册导入、答卷导入、预阅卷等所有会改动考试数据的入口复用，避免出现
某些通道仍可写入、破坏数据一致性的缺口。
"""

from fastapi import HTTPException, status

from app.models.exam import Exam

LOCKED_STATUSES = ("locked", "archived")


def check_exam_modifiable(exam: Exam) -> None:
    """考试处于锁定/归档状态时禁止任何写入操作。"""
    if exam.status in LOCKED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exam is locked or archived",
        )