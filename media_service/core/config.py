from pydantic import Field
from pydantic_settings import SettingsConfigDict,BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    db_url: str = Field(default="postgresql+asyncpg://user:password@media_db:5432/media_processor", validation_alias="MEDIA_DATABASE_URL")
    jwt_secret_key: str = Field(default="your_super_secret_key_here", validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    redis_url:str = Field(default="redis://media_redis:6379", validation_alias="MEDIA_REDIS_URL")
    echo_sql: bool = Field(default=False, validation_alias="ECHO_SQL")

    bucket_name: str = Field(default="media-processor-bucket", validation_alias="BUCKET_NAME")

    minio_url: str = Field(default="minio:9000", validation_alias="MINIO_URL")

    minio_secret_key: str = Field(default="password", validation_alias="MINIO_SECRET_KEY")
    minio_access_key: str = Field(default="admin", validation_alias="MINIO_ACCESS_KEY")

    user_service_url: str = Field(default="http://user_service:8001", validation_alias="USER_SERVICE_URL")

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        extra="ignore"
    )
        


config = Settings()
