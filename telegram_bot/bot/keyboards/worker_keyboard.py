from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import Company, Request, RequestStatus, User, UserLanguage
from services.i18n import t
from services.request_service import RequestService


class WorkerMenuCallback(CallbackData, prefix="worker_menu"):
    action: str


class WorkerRequestSelectCallback(CallbackData, prefix="worker_request_select"):
    request_id: int
    view: str


class WorkerRequestActionCallback(CallbackData, prefix="worker_request_action"):
    action: str
    request_id: int
    view: str


class WorkerDoneConfirmCallback(CallbackData, prefix="worker_done_confirm"):
    action: str
    request_id: int
    view: str


class WorkerAdminMenuCallback(CallbackData, prefix="worker_admin_menu"):
    action: str


class WorkerAdminCompanyCallback(CallbackData, prefix="worker_admin_company"):
    company_id: int


def build_worker_request_list_keyboard(
    requests: list[Request],
    *,
    language: UserLanguage,
    view: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for request in requests:
        title = request.user.display_name if request.user is not None else f"#{request.id}"
        builder.button(
            text=f"{_status_icon(request.status)} #{request.id} | {title}",
            callback_data=WorkerRequestSelectCallback(request_id=request.id, view=view),
        )

    builder.adjust(1)
    return builder.as_markup()


def build_worker_request_actions_keyboard(
    request: Request,
    *,
    language: UserLanguage,
    actor: User,
    view: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if request.status in {RequestStatus.PENDING, RequestStatus.ASSIGNED} and request.accepted_by_worker_id is None:
        builder.button(
            text=t(language, "worker_accept_button"),
            callback_data=WorkerRequestActionCallback(action="accept", request_id=request.id, view=view),
        )

    if request.status != RequestStatus.DONE and request.accepted_by_worker_id == actor.id:
        builder.button(
            text=t(language, "request_done"),
            callback_data=WorkerRequestActionCallback(action="done", request_id=request.id, view=view),
        )

    builder.button(
        text=t(language, "request_back"),
        callback_data=WorkerMenuCallback(action=view),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_worker_done_cancel_keyboard(
    request_id: int,
    *,
    language: UserLanguage,
    view: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "cancel"),
        callback_data=WorkerDoneConfirmCallback(action="cancel", request_id=request_id, view=view),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_worker_done_confirm_keyboard(
    request_id: int,
    *,
    language: UserLanguage,
    view: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "request_done_confirm"),
        callback_data=WorkerDoneConfirmCallback(action="confirm", request_id=request_id, view=view),
    )
    builder.button(
        text=t(language, "cancel"),
        callback_data=WorkerDoneConfirmCallback(action="cancel", request_id=request_id, view=view),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_worker_assignment_message_keyboard(
    request_id: int,
    *,
    language: UserLanguage,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "worker_accept_button"),
        callback_data=WorkerRequestActionCallback(action="accept", request_id=request_id, view="assigned"),
    )
    builder.button(
        text=t(language, "worker_detail_button"),
        callback_data=WorkerRequestSelectCallback(request_id=request_id, view="assigned"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_workers_company_keyboard(
    companies: list[Company],
    *,
    language: UserLanguage,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=company.name,
            callback_data=WorkerAdminCompanyCallback(company_id=company.id),
        )
    builder.button(
        text=t(language, "request_back"),
        callback_data=WorkerAdminMenuCallback(action="back"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_workers_panel_keyboard(
    *,
    language: UserLanguage,
    show_company_switch: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "workers_add"),
        callback_data=WorkerAdminMenuCallback(action="add"),
    )
    if show_company_switch:
        builder.button(
            text=t(language, "menu_companies"),
            callback_data=WorkerAdminMenuCallback(action="companies"),
        )
    builder.button(
        text=t(language, "request_back"),
        callback_data=WorkerAdminMenuCallback(action="back"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_workers_add_cancel_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "request_back"),
        callback_data=WorkerAdminMenuCallback(action="panel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def _status_icon(status: RequestStatus) -> str:
    formatted = RequestService.format_status(status)
    if formatted.startswith("⏳"):
        return "⏳"
    if formatted.startswith("👷"):
        return "👷"
    if formatted.startswith("🛠"):
        return "🛠"
    return "✅"
