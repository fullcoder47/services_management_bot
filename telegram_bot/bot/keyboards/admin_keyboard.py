from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import Company


class AdminMenuCallback(CallbackData, prefix="admin_menu"):
    action: str


class AdminCompanyCallback(CallbackData, prefix="admin_company"):
    company_id: int


class AdminRoleCallback(CallbackData, prefix="admin_role"):
    role: str


class AdminConfirmCallback(CallbackData, prefix="admin_confirm"):
    action: str


def build_admin_company_select_keyboard(companies: list[Company]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for company in companies:
        builder.button(
            text=company.name,
            callback_data=AdminCompanyCallback(company_id=company.id),
        )

    builder.button(
        text="⬅️ Orqaga",
        callback_data=AdminMenuCallback(action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_admin_role_select_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="👨‍💼 Admin",
        callback_data=AdminRoleCallback(role="admin"),
    )
    builder.button(
        text="🛠 Operator",
        callback_data=AdminRoleCallback(role="operator"),
    )
    builder.button(
        text="⬅️ Orqaga",
        callback_data=AdminMenuCallback(action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_admin_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Tasdiqlash",
        callback_data=AdminConfirmCallback(action="confirm"),
    )
    builder.button(
        text="⬅️ Bekor qilish",
        callback_data=AdminConfirmCallback(action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()
