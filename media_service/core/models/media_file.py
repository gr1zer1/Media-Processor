from .base import Base, TimestampMixin
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .media_version import MediaVersionModel
    from .processing_task import ProcessingTaskModel

class MediaFileModel(Base, TimestampMixin):
    original_filename: Mapped[str] = mapped_column(String(255), index=True)
    filetype: Mapped[str] = mapped_column(String(50))
    filesize: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer)

    media_versions: Mapped[list["MediaVersionModel"]] = relationship(
        "MediaVersionModel", back_populates="file"
    )
    processing_task: Mapped["ProcessingTaskModel"] = relationship(
        "ProcessingTaskModel", back_populates="file", uselist=False
    )