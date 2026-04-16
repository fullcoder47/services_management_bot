from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.help_keyboard import build_help_contacts_keyboard
from db.models import User
from services.help_service import HelpContext, HelpService
from services.i18n import button_variants, t
from services.user_service import TelegramUserDTO, UserService


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
    help_context = await HelpService(UserService(session)).get_help_context(user)
    await message.answer(
        _build_help_text(user, help_context),
        reply_markup=build_help_contacts_keyboard(help_context.contacts, user.ui_language),
    )


async def _register_and_sync_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User:
    user_service = UserService(session)
    registration = await user_service.register_or_update(TelegramUserDTO.from_aiogram_user(telegram_user))
    return registration.user


def _build_help_text(actor: User, context: HelpContext) -> str:
    lines = [
        t(actor.ui_language, "help_title"),
        "",
        t(actor.ui_language, context.description_key),
        "",
    ]

    if not context.contacts:
        lines.append(t(actor.ui_language, context.empty_key))
        return "\n".join(lines)

    for contact in context.contacts:
        lines.append(f"• {build_user_profile_link(contact, actor)}")

    return "\n".join(lines).strip()


def build_user_profile_link(user: User, viewer: User) -> str:
    if user.username:
        label = f"@{user.username}"
        return f'<a href="https://t.me/{escape(user.username)}">{label}</a>'
    return (
        f"{escape(user.display_name)}"
        f" ({t(viewer.ui_language, 'help_no_username')}: {user.telegram_id})"
    )
