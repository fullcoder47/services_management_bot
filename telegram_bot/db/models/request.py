from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


class RequestStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class RequestSourceType(StrEnum):
    USER = "user"
    ADMIN = "admin"


request_workers = Table(
    "request_workers",
    Base.metadata,
    Column("request_id", ForeignKey("requests.id", ondelete="CASCADE"), primary_key=True),
    Column("worker_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Request(Base, TimestampMixin):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    accepted_by_worker_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    completed_by_worker_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    problem_text: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    problem_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_type: Mapped[RequestSourceType] = mapped_column(
        Enum(
            RequestSourceType,
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=RequestSourceType.USER,
        nullable=False,
    )
    status: Mapped[RequestStatus] = mapped_column(
        Enum(
            RequestStatus,
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=RequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_image: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="requests",
        foreign_keys=[user_id],
    )
    company: Mapped["Company"] = relationship("Company", back_populates="requests")
    creator_admin: Mapped["User | None"] = relationship(
        "User",
        back_populates="created_admin_requests",
        foreign_keys=[created_by_admin_id],
    )
    accepted_by_worker: Mapped["User | None"] = relationship(
        "User",
        back_populates="accepted_requests",
        foreign_keys=[accepted_by_worker_id],
    )
    completed_by_worker: Mapped["User | None"] = relationship(
        "User",
        back_populates="completed_requests",
        foreign_keys=[completed_by_worker_id],
    )
    assigned_workers: Mapped[list["User"]] = relationship(
        "User",
        secondary=request_workers,
        back_populates="assigned_requests",
    )
    messages: Mapped[list["RequestMessage"]] = relationship(
        "RequestMessage",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="RequestMessage.created_at.asc()",
    )
