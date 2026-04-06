from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.worker_keyboard import (
    WorkerAdminCompanyCallback,
    WorkerAdminMenuCallback,
    build_workers_add_cancel_keyboard,
    build_workers_company_keyboard,
    build_workers_panel_keyboard,
)
from bot.states import WorkersAdminStates
from db.models import Company, User, UserRole
from services.company_service import CompanyService
from services.i18n import button_variants, t
from services.user_service import (
    TelegramUserDTO,
    UserAccessError,
    UserRoleChangeError,
    UserService,
)


router = Router(name=__name__)


@router.message(Command("workers"))
@router.message(F.text.in_(button_variants("menu_workers")))
async def workers_panel_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    await state.clear()
    if actor.is_super_admin:
        text, keyboard = await _build_company_choice_view(session, actor)
        await state.set_state(WorkersAdminStates.waiting_for_company)
        await message.answer(text, reply_markup=keyboard)
        return

    if actor.company_id is None:
        await message.answer(t(actor.ui_language, "users_unassigned_company"))
        return

    company = await CompanyService(session).get_company(actor.company_id)
    if company is None:
        await message.answer(t(actor.ui_language, "users_unassigned_company"))
        return

    await state.update_data(company_id=company.id)
    await _show_workers_panel_message(message, session, actor, company)


@router.callback_query(WorkerAdminMenuCallback.filter(F.action == "companies"))
@router.callback_query(WorkerAdminMenuCallback.filter(F.action == "back"))
async def workers_back_to_companies(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    await state.clear()
    if actor.is_super_admin:
        text, keyboard = await _build_company_choice_view(session, actor)
        await state.set_state(WorkersAdminStates.waiting_for_company)
        if callback.message is not None:
            await _safe_edit_text(callback.message, text, reply_markup=keyboard)
        await callback.answer()
        return

    if actor.company_id is None:
        await callback.answer(t(actor.ui_language, "users_unassigned_company"), show_alert=True)
        return

    company = await CompanyService(session).get_company(actor.company_id)
    if company is None:
        await callback.answer(t(actor.ui_language, "users_unassigned_company"), show_alert=True)
        return

    await state.update_data(company_id=company.id)
    if callback.message is not None:
        await _show_workers_panel_callback(callback.message, session, actor, company)
    await callback.answer()


@router.callback_query(WorkerAdminMenuCallback.filter(F.action == "panel"))
async def workers_panel_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    company = await _resolve_target_company(actor, session, state)
    if company is None:
        await callback.answer(t(actor.ui_language, "workers_choose_company"), show_alert=True)
        return

    if callback.message is not None:
        await _show_workers_panel_callback(callback.message, session, actor, company)
    await callback.answer()


@router.callback_query(WorkerAdminCompanyCallback.filter(), WorkersAdminStates.waiting_for_company)
async def workers_choose_company(
    callback: CallbackQuery,
    callback_data: WorkerAdminCompanyCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    company = await CompanyService(session).get_company(callback_data.company_id)
    if company is None:
        await callback.answer("Kompaniya topilmadi.", show_alert=True)
        return

    if actor.role == UserRole.ADMIN and actor.company_id != company.id:
        await callback.answer(t(actor.ui_language, "users_no_access"), show_alert=True)
        return

    await state.clear()
    await state.update_data(company_id=company.id)
    if callback.message is not None:
        await _show_workers_panel_callback(callback.message, session, actor, company)
    await callback.answer()


@router.callback_query(WorkerAdminMenuCallback.filter(F.action == "add"))
async def workers_add_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    company = await _resolve_target_company(actor, session, state)
    if company is None:
        await callback.answer(t(actor.ui_language, "workers_choose_company"), show_alert=True)
        return

    await state.set_state(WorkersAdminStates.waiting_for_user_id)
    await state.update_data(company_id=company.id)

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            f"{t(actor.ui_language, 'workers_panel_title')}\n\n"
            f"<b>{escape(company.name)}</b>\n\n"
            f"{t(actor.ui_language, 'workers_user_id_prompt')}",
            reply_markup=build_workers_add_cancel_keyboard(actor.ui_language),
        )
    await callback.answer()


@router.message(WorkersAdminStates.waiting_for_user_id)
async def workers_add_capture_user_id(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    company = await _resolve_target_company(actor, session, state)
    if company is None:
        await state.clear()
        await message.answer(t(actor.ui_language, "workers_choose_company"))
        return

    raw_user_id = (message.text or "").strip()
    if not raw_user_id.isdigit():
        await message.answer(
            t(actor.ui_language, "workers_user_id_invalid"),
            reply_markup=build_workers_add_cancel_keyboard(actor.ui_language),
        )
        return

    user_service = UserService(session)
    try:
        worker = await user_service.assign_worker_to_company(actor, int(raw_user_id), company.id)
    except (UserAccessError, UserRoleChangeError) as exc:
        await message.answer(str(exc), reply_markup=build_workers_add_cancel_keyboard(actor.ui_language))
        return

    await state.clear()
    await state.update_data(company_id=company.id)
    await message.answer(
        f"{t(actor.ui_language, 'workers_added_success')}\n"
        f"ID: <b>{worker.telegram_id}</b>\n"
        f"👤 <b>{escape(worker.display_name)}</b>",
    )
    await _show_workers_panel_message(message, session, actor, company)


async def _show_workers_panel_message(
    message: Message,
    session: AsyncSession,
    actor: User,
    company: Company,
) -> None:
    text, keyboard = await _build_workers_panel_view(session, actor, company)
    await message.answer(text, reply_markup=keyboard)


async def _show_workers_panel_callback(
    message: Message,
    session: AsyncSession,
    actor: User,
    company: Company,
) -> None:
    text, keyboard = await _build_workers_panel_view(session, actor, company)
    await _safe_edit_text(message, text, reply_markup=keyboard)


async def _build_company_choice_view(
    session: AsyncSession,
    actor: User,
) -> tuple[str, object | None]:
    companies = await CompanyService(session).list_companies()
    if not companies:
        return t(actor.ui_language, "workers_choose_company"), None
    return (
        f"{t(actor.ui_language, 'workers_panel_title')}\n\n{t(actor.ui_language, 'workers_choose_company')}",
        build_workers_company_keyboard(companies, language=actor.ui_language),
    )


async def _build_workers_panel_view(
    session: AsyncSession,
    actor: User,
    company: Company,
) -> tuple[str, object | None]:
    user_service = UserService(session)
    workers = await user_service.list_workers_for_actor(actor, company.id)

    lines = [
        t(actor.ui_language, "workers_panel_title"),
        "",
        f"🏢 <b>{escape(company.name)}</b>",
        "",
    ]
    if not workers:
        lines.append(t(actor.ui_language, "workers_list_empty"))
    else:
        for worker in workers:
            username = f"@{worker.username}" if worker.username else "-"
            lines.append(
                f"- <b>{escape(worker.display_name)}</b> | {worker.telegram_id} | {escape(username)}"
            )

    return "\n".join(lines), build_workers_panel_keyboard(
        language=actor.ui_language,
        show_company_switch=actor.is_super_admin,
    )


async def _resolve_target_company(
    actor: User,
    session: AsyncSession,
    state: FSMContext,
) -> Company | None:
    if actor.role == UserRole.ADMIN and actor.company_id is not None:
        return await CompanyService(session).get_company(actor.company_id)

    data = await state.get_data()
    company_id = data.get("company_id")
    if not isinstance(company_id, int):
        return None
    return await CompanyService(session).get_company(company_id)


async def _authorize_admin_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        await message.answer(t(user.ui_language, "users_no_access"))
        return None
    return user


async def _authorize_admin_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return None

    user = await _register_and_get_user(callback.from_user, session)
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        await callback.answer(t(user.ui_language, "users_no_access"), show_alert=True)
        return None
    return user


async def _register_and_get_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User:
    user_service = UserService(session)
    registration = await user_service.register_or_update(TelegramUserDTO.from_aiogram_user(telegram_user))
    return registration.user


async def _safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
