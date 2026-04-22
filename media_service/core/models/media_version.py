from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column,relationship
from .base import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .media_file import MediaFileModel


class MediaVersionModel(Base):
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("mediafilemodels.id"), index=True)
    minio_key: Mapped[int] = mapped_column(Integer)
    version_type: Mapped[str] = mapped_column(String(255))
    url: Mapped[int] = mapped_column(Integer)
    file:Mapped["MediaFileModel"] = mapped_column(relationship("MediaFileModel", back_populates="media_versions"))
