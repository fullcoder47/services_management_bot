from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from services.i18n import button_variants, t
from services.user_service import CompanyAdminContacts, TelegramUserDTO, UserService


router = Router(name=__name__)


@router.message(Command("help"))
@router.message(Command("yordam"))
@router.message(F.text.in_(button_variants("menu_help")))
async def help_handler(
    message: Message,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return

    user = await _register_and_sync_user(message.from_user, session)
    user_service = UserService(session)
    contacts = await user_service.get_company_admin_contacts()
    await message.answer(_build_help_text(contacts, user.ui_language))


async def _register_and_sync_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User:
    user_service = UserService(session)
    registration = await user_service.register_or_update(TelegramUserDTO.from_aiogram_user(telegram_user))
    return registration.user


def _build_help_text(contacts: list[CompanyAdminContacts], language) -> str:
    lines = [
        t(language, "help_title"),
        "",
        t(language, "help_text"),
        "",
    ]

    if not contacts:
        lines.append(t(language, "help_no_companies"))
        return "\n".join(lines)

    for contact in contacts:
        lines.append(f"🏢 <b>{escape(contact.company.name)}</b>")
        if contact.admins:
            for admin in contact.admins:
                lines.append(f"• {build_user_profile_link(admin)}")
        else:
            lines.append(f"• {t(language, 'help_no_admin')}")
        lines.append("")

    return "\n".join(lines).strip()


def build_user_profile_link(user: User) -> str:
    label = f"@{user.username}" if user.username else escape(user.display_name)
    if user.username:
        return f'<a href="https://t.me/{escape(user.username)}">{label}</a>'
    return f'<a href="tg://user?id={user.telegram_id}">{label}</a>'
