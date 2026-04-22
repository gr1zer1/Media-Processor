from .base import Base
from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime,timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .media_file import MediaFileModel

class ProcessingTaskModel(Base):
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("mediafiles.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="processing") #pending / processing / done / failed
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True,default=datetime.now(timezone.utc))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    file: Mapped["MediaFileModel"] = relationship(
        "MediaFileModel", back_populates="processing_task"
    )