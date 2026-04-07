from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from services.company_service import CompanyService
from services.i18n import button_variants, t
from services.user_service import UserService


class SubscriptionMiddleware(BaseMiddleware):
    allowed_support_commands = {"/help", "/yordam", "/settings", "/sozlamalar"}

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

        await self._notify_user(event, t(user.ui_language, "inactive_company_block"))
        return None

    async def _notify_user(self, event: TelegramObject, text: str) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
            return

        if isinstance(event, Message):
            await event.answer(text)

    def _is_support_request(self, event: TelegramObject) -> bool:
        if isinstance(event, CallbackQuery):
            data = event.data or ""
            return (
                data.startswith("settings_menu:")
                or data.startswith("settings_language:")
                or data.startswith("settings_company:")
            )

        if not isinstance(event, Message):
            return False

        text = (event.text or "").strip().lower()
        if not text:
            return False

        command = text.split(maxsplit=1)[0]
        command = command.split("@", maxsplit=1)[0]
        help_buttons = {variant.lower() for variant in button_variants("menu_help")}
        dispatcher_buttons = {
            variant.lower() for variant in button_variants("menu_call_dispatcher")
        }
        settings_buttons = {
            variant.lower() for variant in button_variants("menu_settings")
        }
        return (
            command in self.allowed_support_commands
            or text in help_buttons
            or text in dispatcher_buttons
            or text in settings_buttons
        )
