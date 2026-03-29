from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.enums.language import Language
from app.domain.enums.role import Role

if TYPE_CHECKING:
    from app.db.models.user import User


@dataclass(slots=True, frozen=True)
class UserDTO:
    id: int
    telegram_id: int
    full_name: str
    username: str | None
    phone: str | None
    role: Role
    language: Language | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, user: User) -> "UserDTO":
        return cls(
            id=user.id,
            telegram_id=user.telegram_id,
            full_name=user.full_name,
            username=user.username,
            phone=user.phone,
            role=user.role,
            language=user.language,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
