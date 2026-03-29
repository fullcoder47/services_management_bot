from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.localization import language_label
from app.domain.enums.language import Language


class LanguageSelectionCallback(CallbackData, prefix="lang"):
    code: str


def build_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=language_label(Language.UZ),
                    callback_data=LanguageSelectionCallback(code=Language.UZ.value).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=language_label(Language.RU),
                    callback_data=LanguageSelectionCallback(code=Language.RU.value).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=language_label(Language.EN),
                    callback_data=LanguageSelectionCallback(code=Language.EN.value).pack(),
                )
            ],
        ]
    )
