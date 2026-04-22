from .base import Base
from sqlalchemy import DateTime, String,Integer,ForeignKey
from sqlalchemy.orm import Mapped, mapped_column,relationship
from .media_file import MediaFileModel
from datetime import datetime,timezone
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .media_file import MediaFileModel


class ProcessingTaskModel(Base):
    file_id:Mapped[int] = mapped_column(Integer, ForeignKey("mediafilemodel.id"), index=True)
    status:Mapped[str] = mapped_column(String(50), default="pending")
    error_message:Mapped[str] = mapped_column(String(255), nullable=True)
    started_at:Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at:Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    file:Mapped["MediaFileModel"] = mapped_column(relationship("MediaFileModel", back_populates="processing_task"))
