"""应用入口：FastAPI 实例、CORS、统一异常、静态目录、路由挂载、健康检查。

启动时自动建表（幂等）；数据库不可达时应用仍可启动，/health 会暴露数据库状态。
生产环境应改用 Alembic 迁移并移除自动建表。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core import errors
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.base import get_engine, init_db

    try:
        init_db()
        logger.info("数据库表结构已就绪")
    except Exception as exc:  # noqa: BLE001 —— 数据库不可达不阻断应用启动
        logger.warning("数据库初始化失败（应用继续启动，/health 将报告状态）：%s", exc)
    yield
    try:
        get_engine().dispose()
    except Exception:  # noqa: BLE001
        pass


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="直播运营虚拟仿真实训平台 · 教学仿真数据，不连接真实支付",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_body(code: str, message: str, context: dict | None = None) -> dict:
    return {"code": code, "message": message, "context": context or {}}


@app.exception_handler(errors.AppError)
async def app_error_handler(request: Request, exc: errors.AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, exc.context),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_error_body(
            errors.VALIDATION_ERROR,
            "请求参数校验失败：" + "；".join(f"{d['field']} {d['message']}" for d in details[:5]),
            {"details": details},
        ),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=_error_body(errors.INTERNAL_ERROR, f"服务器内部错误：{exc.__class__.__name__}"),
    )


upload_dir = Path(settings.upload_dir)
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(upload_dir)), name="static")

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", tags=["系统"], summary="健康检查")
def health() -> dict:
    from app.db.base import get_engine

    db_status = "ok"
    db_error = None
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_status = "error"
        db_error = str(exc)
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "database_error": db_error,
        "app": settings.app_name,
    }
