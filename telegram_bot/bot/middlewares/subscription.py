from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from services.company_service import CompanyService
from services.user_service import UserService


class SubscriptionMiddleware(BaseMiddleware):
    block_text = "❌ Bu kompaniya vaqtincha faol emas."
    allowed_support_commands = {"/help", "/yordam", "yordam"}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        telegram_user = getattr(event, "from_user", None)

        if not isinstance(session, AsyncSession) or telegram_user is None:
            return await handler(event, data)

        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(telegram_user.id)
        if user is None:
            return await handler(event, data)

        data["current_user"] = user

        if self._is_support_request(event):
            return await handler(event, data)

        if user.is_super_admin or user.company_id is None:
            return await handler(event, data)

        company_service = CompanyService(session)
        company = await company_service.get_company(user.company_id)
        if company is None:
            await user_service.assign_company(user.telegram_id, None)
            return await handler(event, data)

        data["current_company"] = company

        if company_service.check_access(company):
            return await handler(event, data)

        await self._notify_user(event)
        return None

    async def _notify_user(self, event: TelegramObject) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(self.block_text, show_alert=True)
            return

        if isinstance(event, Message):
            await event.answer(self.block_text)

    def _is_support_request(self, event: TelegramObject) -> bool:
        if not isinstance(event, Message):
            return False

        text = (event.text or "").strip().lower()
        if not text:
            return False

        command = text.split(maxsplit=1)[0]
        command = command.split("@", maxsplit=1)[0]
        return command in self.allowed_support_commands
