from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import Company, User, UserLanguage
from services.i18n import t


class AdminRequestMenuCallback(CallbackData, prefix="admin_request_menu"):
    action: str


class AdminRequestCompanyCallback(CallbackData, prefix="admin_request_company"):
    company_id: int


class AdminRequestWorkerToggleCallback(CallbackData, prefix="admin_request_worker"):
    worker_id: int


class AdminRequestConfirmCallback(CallbackData, prefix="admin_request_confirm"):
    action: str


def build_admin_request_cancel_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "cancel"),
        callback_data=AdminRequestMenuCallback(action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_admin_request_optional_image_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "skip"),
        callback_data=AdminRequestMenuCallback(action="skip_image"),
    )
    builder.button(
        text=t(language, "cancel"),
        callback_data=AdminRequestMenuCallback(action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_admin_request_company_keyboard(
    companies: list[Company],
    language: UserLanguage,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=company.name,
            callback_data=AdminRequestCompanyCallback(company_id=company.id),
        )
    builder.button(
        text=t(language, "cancel"),
        callback_data=AdminRequestMenuCallback(action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_admin_request_workers_keyboard(
    workers: list[User],
    selected_worker_ids: set[int],
    language: UserLanguage,
    *,
    allow_confirm: bool = True,
    allow_skip: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for worker in workers:
        prefix = "✅ " if worker.id in selected_worker_ids else ""
        builder.button(
            text=f"{prefix}{worker.display_name} ({worker.telegram_id})",
            callback_data=AdminRequestWorkerToggleCallback(worker_id=worker.id),
        )

    if allow_confirm and selected_worker_ids:
        builder.button(
            text=t(language, "request_done_confirm"),
            callback_data=AdminRequestConfirmCallback(action="confirm_workers"),
        )

    if allow_skip:
        builder.button(
            text=t(language, "skip"),
            callback_data=AdminRequestMenuCallback(action="skip_workers"),
        )

    builder.button(
        text=t(language, "request_back"),
        callback_data=AdminRequestMenuCallback(action="back"),
    )
    builder.button(
        text=t(language, "cancel"),
        callback_data=AdminRequestMenuCallback(action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_admin_request_create_confirm_keyboard(language: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(language, "request_done_confirm"),
        callback_data=AdminRequestConfirmCallback(action="confirm_create"),
    )
    builder.button(
        text=t(language, "request_back"),
        callback_data=AdminRequestMenuCallback(action="back_to_workers"),
    )
    builder.button(
        text=t(language, "cancel"),
        callback_data=AdminRequestMenuCallback(action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()
