from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class ManagerMenuCallback(CallbackData, prefix="manager_menu"):
    action: str


def build_broadcast_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ Bekor qilish",
        callback_data=ManagerMenuCallback(action="cancel_broadcast"),
    )
    builder.adjust(1)
    return builder.as_markup()
