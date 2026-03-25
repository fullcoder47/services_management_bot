from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


class UserRole(StrEnum):
    USER = "user"
    SUPER_ADMIN = "super_admin"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=UserRole.USER,
        nullable=False,
    )

    company: Mapped["Company | None"] = relationship("Company", back_populates="users")

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    @property
    def display_name(self) -> str:
        return self.username or self.first_name
