from pydantic import BaseSettings,Field
from pydantic_settings import SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    db_url: str = Field(default="postgresql+asyncpg://user:password@media_db:5432/media_processor", validation_alias="MEDIA_DATABASE_URL")
    echo_sql: bool = Field(default=False, validation_alias="ECHO_SQL")

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        extra="ignore"
    )


config = Settings()
