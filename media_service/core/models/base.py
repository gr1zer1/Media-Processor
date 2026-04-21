from sqlalchemy.orm import DeclarativeBase,declared_attr, Mapped, mapped_column
from sqlalchemy import DateTime
from datetime import datetime,timezone

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

    @declared_attr
    def __tablename__(cls) -> str:
        if cls.__name__.endswith("Model"):
            return cls.__name__[:-5].lower()
        return cls.__name__.lower()
    

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))