import sys
import types

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


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


TEST_DATABASE_NAME = "media_processor_test"
TEST_DATABASE_URL = (
    f"postgresql+asyncpg://user:password@localhost:5432/{TEST_DATABASE_NAME}"
)
ADMIN_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/postgres"


@pytest_asyncio.fixture(scope="session")
async def test_database():
    admin_engine = create_async_engine(
        ADMIN_DATABASE_URL,
        isolation_level="AUTOCOMMIT",
    )

    async with admin_engine.begin() as conn:
        database_exists = await conn.scalar(
            text(
                "SELECT 1 FROM pg_database WHERE datname = :database_name"
            ),
            {"database_name": TEST_DATABASE_NAME},
        )
        if not database_exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))

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
                {"database_name": TEST_DATABASE_NAME},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}"'))
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def setup_db(test_database):
    engine = create_async_engine(test_database)
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
