from sqlalchemy.orm import DeclarativeBase, declared_attr, Mapped, mapped_column
from datetime import datetime,timezone
from sqlalchemy import DateTime


class Base(DeclarativeBase):

    @declared_attr
    def __tablename__(cls) -> str:
        name = cls.__name__
        if name.endswith("Model"):
            name = name[:-5]
        elif name.endswith("Table"):
            name = name[:-5]
        return f"{name.lower()}s"

    id: Mapped[int] = mapped_column(primary_key=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))