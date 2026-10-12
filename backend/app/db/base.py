"""数据库引擎与会话工厂。

- 目标库为 MySQL（mysql+pymysql）。冒烟测试可用 SQLite 兜底验证业务逻辑，
  两种方言下模型均保持可移植（不使用方言特有类型）。
- 金额一律以「分」存 Integer；时间统一存 UTC（naive），接口序列化时补 Z。
"""

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """统一时间源：UTC naive（存库），序列化时补 Z。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_engine = None
_session_factory: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        kwargs: dict = {"echo": settings.db_echo, "future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["pool_recycle"] = 3600
        _engine = create_engine(url, **kwargs)
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def reset_engine() -> None:
    """供测试脚本切换数据库后重置引擎。"""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def init_db() -> None:
    """建表（幂等）。生产环境应改用 Alembic 迁移。"""
    import app.models  # noqa: F401  确保所有模型已注册到 Base.metadata

    Base.metadata.create_all(bind=get_engine())


__all__ = [
    "Base",
    "Session",
    "utcnow",
    "get_engine",
    "get_session_factory",
    "reset_engine",
    "init_db",
]
