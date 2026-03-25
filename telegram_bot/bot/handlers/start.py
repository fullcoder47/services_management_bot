from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import build_main_menu
from services.users import TelegramUserDTO, UserService


router = Router(name=__name__)


@router.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        await message.answer("Unable to identify your Telegram account.")
        return

    await state.clear()
    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(message.from_user)
    )

    role_text = "super admin" if registration.user.is_super_admin else "user"
    greeting = (
        f"Hello, <b>{registration.user.display_name}</b>!\n\n"
        f"You are registered as: <b>{role_text}</b>.\n"
        f"Created now: <b>{'yes' if registration.created else 'no'}</b>."
    )
    if registration.user.is_super_admin:
        greeting += "\n\nUse <b>/companies</b> to manage companies."

    await message.answer(greeting, reply_markup=build_main_menu())
