from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_repo import UserRepository
from app.domain.dto.user_dto import UserDTO


class AuthContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        data["current_user"] = None

        session = data.get("session")
        from_user = getattr(event, "from_user", None)
        if not isinstance(session, AsyncSession) or from_user is None:
            return await handler(event, data)

        user = await UserRepository(session).get_by_telegram_id(from_user.id)
        if user is not None:
            data["current_user"] = UserDTO.from_model(user)

        return await handler(event, data)
