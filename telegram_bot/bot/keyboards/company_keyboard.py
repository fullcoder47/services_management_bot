from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import Company


class CompanyMenuCallback(CallbackData, prefix="company_menu"):
    action: str


class CompanySelectCallback(CallbackData, prefix="company_select"):
    company_id: int


class CompanyActionCallback(CallbackData, prefix="company_action"):
    action: str
    company_id: int


class CompanyPlanCallback(CallbackData, prefix="company_plan"):
    plan: str


def build_company_list_keyboard(companies: list[Company]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for company in companies:
        status = "🟢 Faol" if company.is_active else "🔴 Nofaol"
        plan_text = "⭐ Premium" if company.plan.value == "premium" else "🆓 Bepul"
        button_text = f"{company.id}. {_trim_text(company.name, 20)} [{plan_text} | {status}]"
        builder.button(
            text=button_text,
            callback_data=CompanySelectCallback(company_id=company.id),
        )

    builder.button(
        text="➕ Kompaniya qo‘shish",
        callback_data=CompanyMenuCallback(action="add"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_company_actions_keyboard(company_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💳 30 kunlik obuna aktiv qilish",
        callback_data=CompanyActionCallback(action="activate", company_id=company_id),
    )
    builder.button(
        text="⛔ Obunani bekor qilish",
        callback_data=CompanyActionCallback(action="deactivate", company_id=company_id),
    )
    builder.button(
        text="🗑 O‘chirish",
        callback_data=CompanyActionCallback(action="delete", company_id=company_id),
    )
    builder.button(
        text="⬅️ Orqaga",
        callback_data=CompanyMenuCallback(action="list"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_company_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ Orqaga",
        callback_data=CompanyMenuCallback(action="list"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_company_plan_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🆓 Bepul",
        callback_data=CompanyPlanCallback(plan="free"),
    )
    builder.button(
        text="⭐ Premium",
        callback_data=CompanyPlanCallback(plan="premium"),
    )
    builder.button(
        text="⬅️ Orqaga",
        callback_data=CompanyMenuCallback(action="list"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."
