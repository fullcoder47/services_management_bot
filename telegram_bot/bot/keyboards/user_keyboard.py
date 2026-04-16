from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.keyboards.request_chat_keyboard import RequestChatOpenCallback
from db.models import Company, Request, UserLanguage
from services.i18n import t
from services.request_service import RequestService


class UserCompanySelectCallback(CallbackData, prefix="user_company_select"):
    company_id: int


class UserRequestMenuCallback(CallbackData, prefix="user_request_menu"):
    action: str


class UserRequestSelectCallback(CallbackData, prefix="user_request_select"):
    request_id: int


class UserLanguageCallback(CallbackData, prefix="user_language"):
    language: str


def build_company_choice_keyboard(companies: list[Company]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=company.name,
            callback_data=UserCompanySelectCallback(company_id=company.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_language_select_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for language in UserLanguage:
        builder.button(
            text=t(language, "lang_name"),
            callback_data=UserLanguageCallback(language=language.value),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_user_phone_keyboard(language: UserLanguage) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(
            text=t(language, "share_phone_button"),
            request_contact=True,
        )
    )
    builder.adjust(1)
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=t(language, "phone_placeholder"),
    )


def build_user_request_list_keyboard(requests: list[Request], language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for request in requests:
        builder.button(
            text=f"#{request.id} | {RequestService.format_status(request.status, language)}",
            callback_data=UserRequestSelectCallback(request_id=request.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_user_request_back_keyboard(
    language: UserLanguage,
    request_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if request_id is not None:
        builder.button(
            text=t(language, "request_chat"),
            callback_data=RequestChatOpenCallback(request_id=request_id, source="user"),
        )
    builder.button(
        text=t(language, "request_back"),
        callback_data=UserRequestMenuCallback(action="list"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_dispatcher_call_keyboard(
    phone_number: str,
    language: UserLanguage,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "dispatcher_call_button"),
        url=f"tel:{phone_number}",
    )
    builder.adjust(1)
    return builder.as_markup()
