from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class MediaVersionModel(Base):
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("mediafilemodels.id"), index=True)
    minio_key: Mapped[int] = mapped_column(Integer)
    version_type: Mapped[str] = mapped_column(String(255))
    url: Mapped[int] = mapped_column(Integer)
