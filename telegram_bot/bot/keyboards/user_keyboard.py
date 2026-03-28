from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from db.models import Company, Request
from services.request_service import RequestService


class UserCompanySelectCallback(CallbackData, prefix="user_company_select"):
    company_id: int


class UserRequestMenuCallback(CallbackData, prefix="user_request_menu"):
    action: str


class UserRequestSelectCallback(CallbackData, prefix="user_request_select"):
    request_id: int


def build_company_choice_keyboard(companies: list[Company]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=company.name,
            callback_data=UserCompanySelectCallback(company_id=company.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_user_phone_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(
            text="📱 Telefonni yuborish",
            request_contact=True,
        )
    )
    builder.adjust(1)
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Telefon raqamingizni yuboring",
    )


def build_user_request_list_keyboard(requests: list[Request]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for request in requests:
        builder.button(
            text=f"#{request.id} | {RequestService.format_status(request.status)}",
            callback_data=UserRequestSelectCallback(request_id=request.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_user_request_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ Orqaga",
        callback_data=UserRequestMenuCallback(action="list"),
    )
    builder.adjust(1)
    return builder.as_markup()
