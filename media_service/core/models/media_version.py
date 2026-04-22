from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .media_file import MediaFileModel

class MediaVersionModel(Base):
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("mediafiles.id"), index=True)
    version_type: Mapped[str] = mapped_column(String(50))  # original/medium/thumbnail/preview
    minio_key: Mapped[str] = mapped_column(String(500))    
    url: Mapped[str] = mapped_column(String(500))          

    file: Mapped["MediaFileModel"] = relationship(
        "MediaFileModel", back_populates="media_versions"
    )