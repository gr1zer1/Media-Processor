from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    database_url: str = Field(default="postgresql+asyncpg://user:password@db:5432/task_manager", validation_alias="DATABASE_URL")
    jwt_secret_key: str = Field(default="top_secret_key", validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, validation_alias="REFRESH_TOKEN_EXPIRE_DAYS")
    echo_sql: bool = Field(default=False, validation_alias="ECHO_SQL")
    redis_url: str = Field(default="redis://localhost:6379", validation_alias="REDIS_URL")

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        extra="ignore"
    )


config = Config()
