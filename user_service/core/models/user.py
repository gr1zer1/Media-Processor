from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class UserModel(Base, TimestampMixin):
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user")
    token_version: Mapped[int] = mapped_column(default=0)
    quota_used: Mapped[int] = mapped_column(default=0)
    quota_limit: Mapped[int] = mapped_column(default=1_073_741_824)
    

