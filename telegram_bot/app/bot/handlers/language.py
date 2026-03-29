from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline.language import LanguageSelectionCallback
from app.bot.keyboards.reply.super_admin import build_super_admin_keyboard
from app.core.config import Settings
from app.domain.enums.language import Language
from app.services import build_auth_service


router = Router(name=__name__)


@router.callback_query(LanguageSelectionCallback.filter())
async def handle_language_selection(
    callback: CallbackQuery,
    callback_data: LanguageSelectionCallback,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    selected_language = Language(callback_data.code)
    auth_service = build_auth_service(session, settings)
    result = await auth_service.process_language_selection(
        telegram_id=callback.from_user.id,
        full_name=callback.from_user.full_name,
        username=callback.from_user.username,
        language=selected_language,
    )

    if callback.message is not None:
        await callback.message.edit_text(result.message)
        if result.is_authorized and result.panel_message and result.language is not None:
            await callback.message.answer(
                result.panel_message,
                reply_markup=build_super_admin_keyboard(result.language),
            )
        await callback.answer()
        return

    await callback.answer(result.message, show_alert=True)
