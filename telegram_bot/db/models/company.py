from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


class CompanyPlan(StrEnum):
    FREE = "free"
    PREMIUM = "premium"


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    dispatcher_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plan: Mapped[CompanyPlan] = mapped_column(
        Enum(
            CompanyPlan,
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=CompanyPlan.FREE,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    users: Mapped[list["User"]] = relationship("User", back_populates="company")
    requests: Mapped[list["Request"]] = relationship("Request", back_populates="company")
    chat_messages: Mapped[list["CompanyChatMessage"]] = relationship(
        "CompanyChatMessage",
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="CompanyChatMessage.created_at.asc()",
    )
