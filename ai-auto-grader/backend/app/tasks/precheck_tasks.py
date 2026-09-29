"""预阅卷相关异步任务。

USE_CELERY=True：交由 Celery Worker 执行（需要 Redis）。
USE_CELERY=False：使用 FastAPI BackgroundTasks 内联执行，无需 Redis。
"""

import logging
from uuid import UUID

from fastapi import BackgroundTasks

from app.core.config import get_settings
from app.services.precheck_service import run_precheck
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="precheck.run")
def run_precheck_task(session_id: str) -> dict:
    run_precheck(session_id)
    return {"session_id": session_id, "status": "done"}


def dispatch_precheck(session_id: UUID, background_tasks: BackgroundTasks) -> str:
    """派发预阅卷任务，返回实际使用的执行模式。"""
    if settings.USE_CELERY:
        try:
            run_precheck_task.delay(str(session_id))
            return "celery"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Celery 派发失败，回退到内联处理: %s", exc)
    background_tasks.add_task(run_precheck, str(session_id))
    return "inline"