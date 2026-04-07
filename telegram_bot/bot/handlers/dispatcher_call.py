from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_keyboard import build_dispatcher_call_keyboard
from db.models import User
from services.company_service import CompanyService
from services.i18n import button_variants, t
from services.user_service import TelegramUserDTO, UserService


router = Router(name=__name__)


@router.message(F.text.in_(button_variants("menu_call_dispatcher")))
async def dispatcher_call_handler(
    message: Message,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return

    user = await _register_and_sync_user(message.from_user, session)
    language = user.ui_language

    if user.company_id is None:
        await message.answer(t(language, "manager_no_company"))
        return

    company_service = CompanyService(session)
    company = await company_service.get_company(user.company_id)
    if company is None or not company.dispatcher_phone:
        await message.answer(t(language, "dispatcher_phone_missing"))
        return

    dial_phone = _normalize_dial_phone(company.dispatcher_phone)
    contact_phone = dial_phone.removeprefix("+")

    await message.answer(
        f"{t(language, 'dispatcher_call_title')}\n\n"
        f"{t(language, 'dispatcher_call_text', company=escape(company.name), phone=escape(dial_phone))}",
        reply_markup=build_dispatcher_call_keyboard(dial_phone, language),
    )

    try:
        contact_name = (company.name[:64] or "Dispatcher").strip()
        await message.answer_contact(
            phone_number=contact_phone,
            first_name=contact_name or "Dispatcher",
        )
    except TelegramBadRequest:
        return


async def _register_and_sync_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User:
    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(telegram_user)
    )
    return registration.user


def _normalize_dial_phone(phone_number: str) -> str:
    normalized = phone_number.strip()
    if normalized.startswith("+"):
        return normalized
    return f"+{normalized}"
