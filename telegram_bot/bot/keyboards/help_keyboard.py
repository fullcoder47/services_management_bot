from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import User, UserLanguage
from services.i18n import t


def build_help_contacts_keyboard(
    contacts: list[User],
    language: UserLanguage,
) -> InlineKeyboardMarkup | None:
    builder = InlineKeyboardBuilder()
    total_buttons = 0
    for user in contacts:
        if not user.username:
            continue
        total_buttons += 1
        builder.button(
            text=f"{t(language, 'help_contact_button')} @{user.username}",
            url=f"https://t.me/{user.username}",
        )

    if total_buttons == 0:
        return None

    builder.adjust(1)
    return builder.as_markup()
