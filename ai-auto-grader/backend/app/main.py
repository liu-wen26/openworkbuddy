from contextlib import asynccontextmanager

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.base import Base, engine
from app.db.migrate import run_migrations
from app import models  # noqa: F401  确保所有模型注册到 Base.metadata
from app.api.v1 import (
    auth, users, exams, templates, imports, choices, grading, precheck, analytics,
    system, exports, archives, notifications, ws,
)
from app.services import realtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    # 绑定主事件循环，供同步业务代码广播实时事件；Celery 模式下额外启动 Redis 中继
    realtime.bind_loop(asyncio.get_running_loop())
    relay_task = realtime.start_redis_relay()
    yield
    if relay_task:
        relay_task.cancel()


settings = get_settings()
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(exams.router, prefix=settings.API_V1_PREFIX)
app.include_router(templates.router, prefix=settings.API_V1_PREFIX)
app.include_router(imports.router, prefix=settings.API_V1_PREFIX)
app.include_router(choices.router, prefix=settings.API_V1_PREFIX)
app.include_router(grading.router, prefix=settings.API_V1_PREFIX)
app.include_router(precheck.router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics.router, prefix=settings.API_V1_PREFIX)
app.include_router(system.router, prefix=settings.API_V1_PREFIX)
app.include_router(exports.router, prefix=settings.API_V1_PREFIX)
app.include_router(archives.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(ws.router, prefix=settings.API_V1_PREFIX)


@app.middleware("http")
async def audit_middleware(request, call_next):
    """F9-03：对 API 写操作统一记录审计日志（失败不阻断请求）。"""
    response = await call_next(request)
    try:
        if (
            request.url.path.startswith(settings.API_V1_PREFIX)
            and request.method in ("POST", "PUT", "PATCH", "DELETE")
            # 登录由 auth 端点显式记录（含用户归属），中间件避免重复且无归属的记录
            and request.url.path != f"{settings.API_V1_PREFIX}/auth/login"
        ):
            from app.services import audit_service

            user_id = None
            authorization = request.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                payload = decode_token(authorization[7:])
                if payload:
                    user_id = payload.sub
            audit_service.record_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                user_id=user_id,
            )
    except Exception:  # noqa: BLE001  审计不应影响响应
        pass
    return response


@app.get("/health")
def health_check():
    return {"status": "ok"}
