from __future__ import annotations

from sqlalchemy import BIGINT, Boolean, Enum as SqlEnum, Index, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.domain.enums.language import Language
from app.domain.enums.role import Role


def _enum_values(enum_cls: type[Role] | type[Language]) -> list[str]:
    return [member.value for member in enum_cls]


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_role", "role"),
        Index("ix_users_language", "language"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BIGINT, unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role: Mapped[Role] = mapped_column(
        SqlEnum(Role, name="user_role", values_callable=_enum_values),
        nullable=False,
    )
    language: Mapped[Language | None] = mapped_column(
        SqlEnum(Language, name="user_language", values_callable=_enum_values),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
