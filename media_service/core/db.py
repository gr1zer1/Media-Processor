from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator
from .config import config
from minio import Minio

class DBHelper:


    def __init__(self, db_url: str, echo: bool = False,max_overflow: int = 10,pool_timeout: int = 30,pool_size: int = 10):
        self.db_url = db_url
        self.echo = echo
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_size = pool_size
        self.engine = create_async_engine(
            self.db_url,
            echo=self.echo,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_size=self.pool_size,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

        self.minio_client = Minio(
            config.minio_url,
            access_key="admin",
            secret_key="password",
            secure=False,
        )
    async def get_session(self) -> AsyncGenerator[AsyncSession, None, None]:
        async with self.session_factory() as session:
            yield session
    
    async def db_dispose(self):
        await self.engine.dispose()




db_helper = DBHelper(
    db_url=config.db_url,
)