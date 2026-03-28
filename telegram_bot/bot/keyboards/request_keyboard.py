from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import Request, RequestStatus


class RequestMenuCallback(CallbackData, prefix="request_menu"):
    action: str


class RequestSelectCallback(CallbackData, prefix="request_select"):
    request_id: int


class RequestActionCallback(CallbackData, prefix="request_action"):
    action: str
    request_id: int


class RequestDoneConfirmCallback(CallbackData, prefix="request_done_confirm"):
    action: str
    request_id: int


def build_request_create_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ Bekor qilish",
        callback_data=RequestMenuCallback(action="cancel_create"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_optional_image_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⏭️ O‘tkazib yuborish",
        callback_data=RequestMenuCallback(action="skip_image"),
    )
    builder.button(
        text="⬅️ Bekor qilish",
        callback_data=RequestMenuCallback(action="cancel_create"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_done_cancel_keyboard(request_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ Bekor qilish",
        callback_data=RequestDoneConfirmCallback(action="cancel", request_id=request_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_admin_actions_keyboard(request: Request) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if request.status == RequestStatus.PENDING:
        builder.button(
            text="✅ Qabul qilish",
            callback_data=RequestActionCallback(action="accept", request_id=request.id),
        )
    if request.status != RequestStatus.DONE:
        builder.button(
            text="✔️ Bajarildi",
            callback_data=RequestActionCallback(action="done", request_id=request.id),
        )
    builder.button(
        text="⬅️ Orqaga",
        callback_data=RequestMenuCallback(action="list"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_done_confirm_keyboard(request_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Tasdiqlash",
        callback_data=RequestDoneConfirmCallback(action="confirm", request_id=request_id),
    )
    builder.button(
        text="⬅️ Bekor qilish",
        callback_data=RequestDoneConfirmCallback(action="cancel", request_id=request_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_list_keyboard(requests: list[Request]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for request in requests:
        user_name = request.user.display_name if request.user is not None else "Noma'lum user"
        status = _status_icon(request.status)
        builder.button(
            text=f"{status} #{request.id} | {user_name}",
            callback_data=RequestSelectCallback(request_id=request.id),
        )

    builder.adjust(1)
    return builder.as_markup()


def _status_icon(status: RequestStatus) -> str:
    if status == RequestStatus.PENDING:
        return "⏳"
    if status == RequestStatus.IN_PROGRESS:
        return "🛠"
    return "✅"
