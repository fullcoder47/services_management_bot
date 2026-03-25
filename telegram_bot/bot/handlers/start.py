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
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return

    await state.clear()
    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(message.from_user)
    )

    role_text = "super admin" if registration.user.is_super_admin else "foydalanuvchi"
    created_text = "ha" if registration.created else "yo'q"
    greeting = (
        f"Salom, <b>{registration.user.display_name}</b>!\n\n"
        f"Sizning rolingiz: <b>{role_text}</b>.\n"
        f"Hozir ro'yxatdan o'tdingizmi: <b>{created_text}</b>."
    )
    if registration.user.is_super_admin:
        greeting += "\n\nKompaniyalarni boshqarish uchun <b>/companies</b> yoki <b>Kompaniyalar</b> tugmasidan foydalaning."

    await message.answer(greeting, reply_markup=build_main_menu())
