from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import build_main_menu
from db.models import UserRole
from services.user_service import TelegramUserDTO, UserService


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

    greeting = (
        f"Salom, <b>{registration.user.display_name}</b>!\n\n"
        f"Sizning rolingiz: <b>{_format_role(registration.user.role)}</b>.\n"
    )
    greeting += (
        "Siz botda muvaffaqiyatli ro'yxatdan o'tdingiz."
        if registration.created
        else "Siz allaqachon ro'yxatdan o'tgansiz."
    )

    if registration.user.is_super_admin:
        greeting += (
            "\n\nKompaniyalarni boshqarish uchun <b>/companies</b> yoki <b>Kompaniyalar</b> tugmasidan foydalaning."
            "\nAdmin boshqaruvi uchun esa <b>👤 Adminlar</b> tugmasini bosing."
        )

    await message.answer(greeting, reply_markup=build_main_menu())


def _format_role(role: UserRole) -> str:
    if role == UserRole.SUPER_ADMIN:
        return "super admin"
    if role == UserRole.ADMIN:
        return "admin"
    if role == UserRole.OPERATOR:
        return "operator"
    return "foydalanuvchi"
