import sys
import types
import os
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from dotenv import dotenv_values


class FakeRedisClient:
    def __init__(self):
        self.storage = {}
        self.last_set = None

    def __await__(self):
        async def _return_self():
            return self

        return _return_self().__await__()

    async def get(self, key):
        return self.storage.get(key)

    async def set(self, key, value, ex=None):
        self.storage[key] = value
        self.last_set = {"key": key, "value": value, "ex": ex}


def _install_redis_stub():
    if "redis.asyncio" in sys.modules:
        return

    redis_module = types.ModuleType("redis")
    redis_asyncio_module = types.ModuleType("redis.asyncio")

    def from_url(_url):
        return FakeRedisClient()

    redis_asyncio_module.Redis = FakeRedisClient
    redis_asyncio_module.from_url = from_url
    redis_module.asyncio = redis_asyncio_module

    sys.modules["redis"] = redis_module
    sys.modules["redis.asyncio"] = redis_asyncio_module


def _install_fastapi_limiter_stub():
    if "fastapi_limiter.depends" in sys.modules:
        return

    fastapi_limiter_module = types.ModuleType("fastapi_limiter")
    depends_module = types.ModuleType("fastapi_limiter.depends")

    class FastAPILimiter:
        @staticmethod
        async def init(_redis):
            return None

    class RateLimiter:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __call__(self):
            return None

    fastapi_limiter_module.FastAPILimiter = FastAPILimiter
    depends_module.RateLimiter = RateLimiter

    sys.modules["fastapi_limiter"] = fastapi_limiter_module
    sys.modules["fastapi_limiter.depends"] = depends_module


_install_redis_stub()
_install_fastapi_limiter_stub()

from core import Base, UserModel  # noqa: E402
from core.db import db_helper  # noqa: E402
from main import app  # noqa: E402

PROJECT_ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
DEFAULT_TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}_test".format(
        user=os.getenv("POSTGRES_USER", PROJECT_ENV.get("POSTGRES_USER", "user")),
        password=os.getenv(
            "POSTGRES_PASSWORD", PROJECT_ENV.get("POSTGRES_PASSWORD", "password")
        ),
        host=os.getenv("TEST_DATABASE_HOST", "localhost"),
        port=os.getenv("TEST_DATABASE_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", PROJECT_ENV.get("POSTGRES_DB", "media_processor")),
    ),
)
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


@pytest_asyncio.fixture(scope="session")
async def test_database():
    if make_url(TEST_DATABASE_URL).get_backend_name() != "postgresql":
        yield TEST_DATABASE_URL
        return

    test_database_name = make_url(TEST_DATABASE_URL).database
    admin_database_url = make_url(TEST_DATABASE_URL).set(database="postgres")
    admin_engine = create_async_engine(
        admin_database_url,
        isolation_level="AUTOCOMMIT",
    )

    async with admin_engine.begin() as conn:
        database_exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": test_database_name},
        )
        if not database_exists:
            await conn.execute(text(f'CREATE DATABASE "{test_database_name}"'))

    try:
        yield TEST_DATABASE_URL
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name
                    AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": test_database_name},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{test_database_name}"'))
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def setup_db(test_database):
    engine_kwargs = {}
    if make_url(test_database).get_backend_name() == "sqlite":
        engine_kwargs = {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        }

    engine = create_async_engine(test_database, **engine_kwargs)
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    fake_redis = FakeRedisClient()

    old_engine = db_helper.engine
    old_session_factory = db_helper.session_factory
    old_redis_pool = db_helper.redis_pool

    db_helper.engine = engine
    db_helper.session_factory = session_factory
    db_helper.redis_pool = fake_redis

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield {
            "engine": engine,
            "session_factory": session_factory,
            "redis": fake_redis,
        }
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
        db_helper.engine = old_engine
        db_helper.session_factory = old_session_factory
        db_helper.redis_pool = old_redis_pool
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(setup_db):
    del setup_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
    ) as async_client:
        yield async_client
