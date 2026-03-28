from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import UserLanguage
from services.i18n import t


class ManagerMenuCallback(CallbackData, prefix="manager_menu"):
    action: str
    target: str | None = None


def build_broadcast_cancel_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "cancel"),
        callback_data=ManagerMenuCallback(action="cancel_broadcast"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_broadcast_target_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "broadcast_target_admins"),
        callback_data=ManagerMenuCallback(action="choose_target", target="admins"),
    )
    builder.button(
        text=t(language, "broadcast_target_users"),
        callback_data=ManagerMenuCallback(action="choose_target", target="users"),
    )
    builder.button(
        text=t(language, "broadcast_target_all"),
        callback_data=ManagerMenuCallback(action="choose_target", target="all"),
    )
    builder.button(
        text=t(language, "cancel"),
        callback_data=ManagerMenuCallback(action="cancel_broadcast"),
    )
    builder.adjust(1)
    return builder.as_markup()
