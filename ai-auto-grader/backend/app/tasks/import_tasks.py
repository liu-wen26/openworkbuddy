"""导入相关异步任务。

USE_CELERY=True：交由 Celery Worker 执行（需要 Redis）。
USE_CELERY=False：使用 FastAPI BackgroundTasks 内联执行，无需 Redis，便于单机部署与演示。
"""

import logging
from uuid import UUID

from fastapi import BackgroundTasks

from app.core.config import get_settings
from app.services.import_service import process_batch
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="imports.process_batch")
def process_import_batch(batch_id: str) -> dict:
    process_batch(batch_id)
    return {"batch_id": batch_id, "status": "done"}


def dispatch_process_batch(batch_id: UUID, background_tasks: BackgroundTasks) -> str:
    """派发批次处理任务，返回实际使用的执行模式。"""
    if settings.USE_CELERY:
        try:
            process_import_batch.delay(str(batch_id))
            return "celery"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Celery 派发失败，回退到内联处理: %s", exc)
    background_tasks.add_task(process_batch, str(batch_id))
    return "inline"