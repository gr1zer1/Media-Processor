from pydantic import BaseSettings,Field
from pydantic_settings import SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    db_url: str = Field(default="postgresql+asyncpg://user:password@media_db:5432/media_processor", validation_alias="MEDIA_DATABASE_URL")
    jwt_secret_key: str = Field(default="your_super_secret_key_here", validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    echo_sql: bool = Field(default=False, validation_alias="ECHO_SQL")

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        extra="ignore"
    )


config = Settings()
