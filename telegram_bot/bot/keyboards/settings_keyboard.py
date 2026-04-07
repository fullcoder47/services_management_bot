from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import Company, UserLanguage
from services.i18n import t


class SettingsMenuCallback(CallbackData, prefix="settings_menu"):
    action: str


class SettingsLanguageCallback(CallbackData, prefix="settings_language"):
    language: str


class SettingsCompanyCallback(CallbackData, prefix="settings_company"):
    company_id: int


def build_settings_menu_keyboard(
    language: UserLanguage,
    *,
    can_change_company: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "settings_change_language"),
        callback_data=SettingsMenuCallback(action="language"),
    )
    builder.button(
        text=t(language, "settings_change_phone"),
        callback_data=SettingsMenuCallback(action="phone"),
    )
    if can_change_company:
        builder.button(
            text=t(language, "settings_change_company"),
            callback_data=SettingsMenuCallback(action="company"),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_settings_language_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in UserLanguage:
        builder.button(
            text=t(item, "lang_name"),
            callback_data=SettingsLanguageCallback(language=item.value),
        )
    builder.button(
        text=t(language, "settings_back"),
        callback_data=SettingsMenuCallback(action="open"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_settings_company_keyboard(
    companies: list[Company],
    language: UserLanguage,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=company.name,
            callback_data=SettingsCompanyCallback(company_id=company.id),
        )
    builder.button(
        text=t(language, "settings_back"),
        callback_data=SettingsMenuCallback(action="open"),
    )
    builder.adjust(1)
    return builder.as_markup()
