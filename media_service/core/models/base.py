from sqlalchemy.orm import DeclarativeBase,declared_attr, Mapped, mapped_column

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

    @declared_attr
    def __tablename__(cls) -> str:
        if cls.__name__.endswith("Model"):
            return cls.__name__[:-5].lower()
        return cls.__name__.lower()
    