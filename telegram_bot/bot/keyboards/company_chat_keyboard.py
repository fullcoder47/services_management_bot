from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import Company, CompanyChatChannel, UserLanguage
from services.i18n import t


class CompanyChatMenuCallback(CallbackData, prefix="company_chat"):
    action: str
    channel: str
    company_id: int


def build_company_chat_user_root_keyboard(
    language: UserLanguage,
    company_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "company_chat_open_company_chat"),
        callback_data=CompanyChatMenuCallback(
            action="open",
            channel=CompanyChatChannel.COMPANY_USERS.value,
            company_id=company_id,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_company_chat_admin_root_keyboard(
    language: UserLanguage,
    company_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "company_chat_with_users"),
        callback_data=CompanyChatMenuCallback(
            action="open",
            channel=CompanyChatChannel.COMPANY_USERS.value,
            company_id=company_id,
        ),
    )
    builder.button(
        text=t(language, "company_chat_with_super_admin"),
        callback_data=CompanyChatMenuCallback(
            action="open",
            channel=CompanyChatChannel.COMPANY_ADMINS.value,
            company_id=company_id,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_company_chat_super_admin_root_keyboard(
    language: UserLanguage,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "company_chat_with_users"),
        callback_data=CompanyChatMenuCallback(
            action="companies",
            channel=CompanyChatChannel.COMPANY_USERS.value,
            company_id=0,
        ),
    )
    builder.button(
        text=t(language, "company_chat_with_admins"),
        callback_data=CompanyChatMenuCallback(
            action="companies",
            channel=CompanyChatChannel.COMPANY_ADMINS.value,
            company_id=0,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_company_chat_company_list_keyboard(
    companies: list[Company],
    language: UserLanguage,
    channel: CompanyChatChannel,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=f"#{company.id} | {company.name}",
            callback_data=CompanyChatMenuCallback(
                action="open",
                channel=channel.value,
                company_id=company.id,
            ),
        )

    builder.button(
        text=t(language, "company_chat_back"),
        callback_data=CompanyChatMenuCallback(
            action="root",
            channel=channel.value,
            company_id=0,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_company_chat_view_keyboard(
    language: UserLanguage,
    company_id: int,
    channel: CompanyChatChannel,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "company_chat_back"),
        callback_data=CompanyChatMenuCallback(
            action="back",
            channel=channel.value,
            company_id=company_id,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_company_chat_notification_keyboard(
    language: UserLanguage,
    company_id: int,
    channel: CompanyChatChannel,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "menu_request_chat"),
        callback_data=CompanyChatMenuCallback(
            action="open",
            channel=channel.value,
            company_id=company_id,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()
