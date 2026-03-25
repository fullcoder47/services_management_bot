from __future__ import annotations

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.company_keyboard import (
    CompanyActionCallback,
    CompanyMenuCallback,
    CompanyPlanCallback,
    CompanySelectCallback,
    build_company_actions_keyboard,
    build_company_cancel_keyboard,
    build_company_list_keyboard,
    build_company_plan_keyboard,
)
from db.models import Company, CompanyPlan, User
from services.company_service import (
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    CompanyService,
    CreateCompanyDTO,
)
from services.users import TelegramUserDTO, UserService


router = Router(name=__name__)


class CompanyCreateStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_plan = State()


@router.message(Command("companies"))
async def companies_command(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_message(message, session)
    if admin is None:
        return

    await state.clear()
    text, keyboard = await _build_company_list_view(session)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(CompanyMenuCallback.filter(F.action == "list"))
async def companies_list_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_callback(callback, session)
    if admin is None:
        return

    await state.clear()
    text, keyboard = await _build_company_list_view(session)
    if callback.message is not None:
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(CompanyMenuCallback.filter(F.action == "add"))
async def start_company_create(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_callback(callback, session)
    if admin is None:
        return

    await state.clear()
    await state.set_state(CompanyCreateStates.waiting_for_name)

    if callback.message is not None:
        await callback.message.edit_text(
            "Send the company name.",
            reply_markup=build_company_cancel_keyboard(),
        )
    await callback.answer()


@router.message(CompanyCreateStates.waiting_for_name)
async def capture_company_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_message(message, session)
    if admin is None:
        return

    company_name = (message.text or "").strip()
    if not company_name:
        await message.answer("Company name cannot be empty. Send a valid company name.")
        return

    await state.update_data(company_name=company_name)
    await state.set_state(CompanyCreateStates.waiting_for_plan)
    await message.answer(
        "Choose the company plan.",
        reply_markup=build_company_plan_keyboard(),
    )


@router.callback_query(CompanyPlanCallback.filter(), CompanyCreateStates.waiting_for_plan)
async def create_company_from_plan(
    callback: CallbackQuery,
    callback_data: CompanyPlanCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_callback(callback, session)
    if admin is None:
        return

    data = await state.get_data()
    company_name = str(data.get("company_name", "")).strip()
    if not company_name:
        await state.clear()
        if callback.message is not None:
            text, keyboard = await _build_company_list_view(session)
            await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer("Company name was lost. Start again.", show_alert=True)
        return

    company_service = CompanyService(session)
    try:
        company = await company_service.create_company(
            CreateCompanyDTO(
                name=company_name,
                plan=CompanyPlan(callback_data.plan),
            )
        )
    except CompanyAlreadyExistsError as exc:
        await state.set_state(CompanyCreateStates.waiting_for_name)
        if callback.message is not None:
            await callback.message.edit_text(
                f"{exc}\n\nSend a different company name.",
                reply_markup=build_company_cancel_keyboard(),
            )
        await callback.answer("Company name already exists.", show_alert=True)
        return

    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            "Company created successfully.\n\n" + _format_company_details(company),
            reply_markup=build_company_actions_keyboard(company.id),
        )
    await callback.answer("Company created.")


@router.message(CompanyCreateStates.waiting_for_plan)
async def waiting_for_plan_hint(
    message: Message,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_message(message, session)
    if admin is None:
        return

    await message.answer(
        "Use the inline buttons to choose a plan.",
        reply_markup=build_company_plan_keyboard(),
    )


@router.callback_query(CompanySelectCallback.filter())
async def company_details_callback(
    callback: CallbackQuery,
    callback_data: CompanySelectCallback,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_callback(callback, session)
    if admin is None:
        return

    company_service = CompanyService(session)
    company = await company_service.get_company(callback_data.company_id)
    if company is None:
        await callback.answer("Company not found.", show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(
            _format_company_details(company),
            reply_markup=build_company_actions_keyboard(company.id),
        )
    await callback.answer()


@router.callback_query(CompanyActionCallback.filter(F.action == "activate"))
async def activate_company_subscription(
    callback: CallbackQuery,
    callback_data: CompanyActionCallback,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_callback(callback, session)
    if admin is None:
        return

    company_service = CompanyService(session)
    try:
        company = await company_service.activate_subscription(callback_data.company_id, days=30)
    except CompanyNotFoundError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(
            "Subscription activated for 30 days.\n\n" + _format_company_details(company),
            reply_markup=build_company_actions_keyboard(company.id),
        )
    await callback.answer("Subscription activated.")


@router.callback_query(CompanyActionCallback.filter(F.action == "delete"))
async def delete_company_callback(
    callback: CallbackQuery,
    callback_data: CompanyActionCallback,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_callback(callback, session)
    if admin is None:
        return

    company_service = CompanyService(session)
    deleted = await company_service.delete_company(callback_data.company_id)
    if not deleted:
        await callback.answer("Company not found.", show_alert=True)
        return

    text, keyboard = await _build_company_list_view(session)
    if callback.message is not None:
        await callback.message.edit_text(
            "Company deleted.\n\n" + text,
            reply_markup=keyboard,
        )
    await callback.answer("Company deleted.")


async def _build_company_list_view(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    company_service = CompanyService(session)
    companies = await company_service.list_companies()

    lines = ["<b>Company management</b>", ""]
    if not companies:
        lines.append("No companies created yet.")
    else:
        lines.append("Companies:")
        for company in companies:
            status = "active" if company.is_active else "inactive"
            access = "allowed" if company.is_active else "blocked"
            lines.append(
                f"{company.id}. <b>{company.name}</b> | {company.plan.value} | {status} | access {access}"
            )

    return "\n".join(lines), build_company_list_keyboard(companies)


async def _authorize_super_admin_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Unable to identify your Telegram account.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user is None or not user.is_super_admin:
        await message.answer("Only super admins can manage companies.")
        return None
    return user


async def _authorize_super_admin_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Unable to identify your Telegram account.", show_alert=True)
        return None

    user = await _register_and_get_user(callback.from_user, session)
    if user is None or not user.is_super_admin:
        await callback.answer("Only super admins can manage companies.", show_alert=True)
        return None
    return user


async def _register_and_get_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User | None:
    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(telegram_user)
    )
    return registration.user


def _format_company_details(company: Company) -> str:
    access_text = "allowed" if company.is_active else "blocked"
    return (
        f"<b>Company #{company.id}</b>\n"
        f"Name: <b>{company.name}</b>\n"
        f"Plan: <b>{company.plan.value}</b>\n"
        f"Active: <b>{'yes' if company.is_active else 'no'}</b>\n"
        f"Subscription end: <b>{_format_subscription_end(company.subscription_end)}</b>\n"
        f"Access: <b>{access_text}</b>"
    )


def _format_subscription_end(subscription_end: datetime | None) -> str:
    if subscription_end is None:
        return "not activated"

    normalized = subscription_end if subscription_end.tzinfo else subscription_end.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
