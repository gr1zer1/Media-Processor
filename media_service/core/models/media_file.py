from .base import Base,TimestampMixin
from sqlalchemy import String,Integer
from sqlalchemy.orm import Mapped, mapped_column


class MediaFileModel(Base, TimestampMixin):
    original_filename: Mapped[str] = mapped_column(String(255),index=True)
    filetype: Mapped[str] = mapped_column(String(255))
    filesize: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer)