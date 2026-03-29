from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.domain.enums.language import Language
from app.services.localization_service import LocalizationService


_localization_service = LocalizationService()


def build_super_admin_keyboard(language: Language) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=_localization_service.companies_button(language))],
            [KeyboardButton(text=_localization_service.statistics_button(language))],
            [KeyboardButton(text=_localization_service.settings_button(language))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def companies_button_labels() -> set[str]:
    return {_localization_service.companies_button(language) for language in Language}


def statistics_button_labels() -> set[str]:
    return {_localization_service.statistics_button(language) for language in Language}


def settings_button_labels() -> set[str]:
    return {_localization_service.settings_button(language) for language in Language}
