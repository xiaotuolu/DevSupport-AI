# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""数据库连接与会话管理。

- 应用运行时：异步引擎（aiomysql）+ AsyncSession。
- 脚本（建表/灌数据）：同步引擎（pymysql）+ Session。
两者共享同一套 ORM 模型（Base）。
"""

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# ----- 异步（应用运行时） -----
async_engine = create_async_engine(
    settings.mysql_dsn_async,
    # 注意：aiomysql 0.2 的 ping() 签名与 SQLAlchemy pre_ping 不兼容，故关闭；
    # 用 pool_recycle 回收旧连接以避免 MySQL 主动断连。
    pool_pre_ping=False,
    pool_recycle=1800,
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供异步数据库会话。"""
    async with AsyncSessionLocal() as session:
        yield session


# ----- 同步（脚本） -----
sync_engine = create_engine(settings.mysql_dsn_sync, pool_pre_ping=True, echo=False)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)
