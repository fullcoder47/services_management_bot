from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import UserLanguage
from services.i18n import t


class RequestChatOpenCallback(CallbackData, prefix="request_chat_open"):
    request_id: int
    source: str


class RequestChatMenuCallback(CallbackData, prefix="request_chat_menu"):
    action: str
    request_id: int
    source: str


def build_request_chat_view_keyboard(
    request_id: int,
    language: UserLanguage,
    source: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "request_back"),
        callback_data=RequestChatMenuCallback(action="back", request_id=request_id, source=source),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_chat_notification_keyboard(
    request_id: int,
    language: UserLanguage,
    source: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "request_chat"),
        callback_data=RequestChatOpenCallback(request_id=request_id, source=source),
    )
    builder.adjust(1)
    return builder.as_markup()
