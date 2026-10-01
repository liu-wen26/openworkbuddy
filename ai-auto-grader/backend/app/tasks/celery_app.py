from celery import Celery

from app.core.config import get_settings

settings = get_settings()

# Celery 应用：仅当 settings.USE_CELERY=True 时才需要 Redis broker。
celery_app = Celery(
    "auto_grader",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.autodiscover_tasks(["app.tasks"])