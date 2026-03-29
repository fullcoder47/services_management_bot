from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline.language import build_language_keyboard
from app.bot.keyboards.reply.super_admin import build_super_admin_keyboard
from app.core.config import Settings
from app.services import build_auth_service


router = Router(name=__name__)


@router.message(CommandStart())
async def handle_start(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    auth_service = build_auth_service(session, settings)
    result = await auth_service.process_start(
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
    )

    if result.requires_language_selection:
        await message.answer(
            result.message,
            reply_markup=build_language_keyboard(),
        )
        return

    if result.is_authorized and result.language is not None:
        await message.answer(
            result.message,
            reply_markup=build_super_admin_keyboard(result.language),
        )
        return

    await message.answer(
        result.message,
        reply_markup=ReplyKeyboardRemove(),
    )
