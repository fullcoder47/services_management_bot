from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import Request, RequestStatus, UserLanguage
from services.i18n import t


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


class RequestRejectConfirmCallback(CallbackData, prefix="request_reject_confirm"):
    action: str
    request_id: int


def build_request_create_cancel_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "cancel"),
        callback_data=RequestMenuCallback(action="cancel_create"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_optional_image_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "skip"),
        callback_data=RequestMenuCallback(action="skip_image"),
    )
    builder.button(
        text=t(language, "cancel"),
        callback_data=RequestMenuCallback(action="cancel_create"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_done_cancel_keyboard(request_id: int, language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "cancel"),
        callback_data=RequestDoneConfirmCallback(action="cancel", request_id=request_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_admin_actions_keyboard(
    request: Request,
    language: UserLanguage,
    *,
    can_reject: bool = False,
    can_assign_workers: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if request.status == RequestStatus.PENDING:
        builder.button(
            text=t(language, "request_accept"),
            callback_data=RequestActionCallback(action="accept", request_id=request.id),
        )
    if can_reject and request.status != RequestStatus.DONE:
        builder.button(
            text=t(language, "request_reject"),
            callback_data=RequestActionCallback(action="reject", request_id=request.id),
        )
    if can_assign_workers and request.status != RequestStatus.DONE:
        builder.button(
            text=t(language, "request_assign_workers"),
            callback_data=RequestActionCallback(action="assign_workers", request_id=request.id),
        )
    if request.status != RequestStatus.DONE:
        builder.button(
            text=t(language, "request_done"),
            callback_data=RequestActionCallback(action="done", request_id=request.id),
        )
    builder.button(
        text=t(language, "request_back"),
        callback_data=RequestMenuCallback(action="list"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_done_confirm_keyboard(request_id: int, language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "request_done_confirm"),
        callback_data=RequestDoneConfirmCallback(action="confirm", request_id=request_id),
    )
    builder.button(
        text=t(language, "cancel"),
        callback_data=RequestDoneConfirmCallback(action="cancel", request_id=request_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_reject_confirm_keyboard(
    request_id: int,
    language: UserLanguage,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "request_reject_confirm_yes"),
        callback_data=RequestRejectConfirmCallback(action="confirm", request_id=request_id),
    )
    builder.button(
        text=t(language, "request_reject_confirm_no"),
        callback_data=RequestRejectConfirmCallback(action="cancel", request_id=request_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_request_list_keyboard(
    requests: list[Request],
    *,
    language: UserLanguage,
    include_export: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for request in requests:
        user_name = request.user.display_name if request.user is not None else "-"
        builder.button(
            text=f"{_status_icon(request.status)} #{request.id} | {user_name}",
            callback_data=RequestSelectCallback(request_id=request.id),
        )

    if include_export:
        builder.button(
            text=t(language, "requests_export"),
            callback_data=RequestMenuCallback(action="export_excel"),
        )

    builder.adjust(1)
    return builder.as_markup()


def _status_icon(status: RequestStatus) -> str:
    if status == RequestStatus.PENDING:
        return "⏳"
    if status == RequestStatus.ASSIGNED:
        return "👷"
    if status == RequestStatus.IN_PROGRESS:
        return "🛠"
    return "✅"
