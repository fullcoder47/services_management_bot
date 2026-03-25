from __future__ import annotations

from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
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
from db.models import Company, CompanyPlan, User, UserRole
from services.company_service import (
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    CompanyService,
    CreateCompanyDTO,
    normalize_utc_datetime,
)
from services.users import (
    TelegramUserDTO,
    UserNotFoundError,
    UserRoleChangeError,
    UserService,
)


router = Router(name=__name__)


class CompanyManagementStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_plan = State()
    waiting_for_user_telegram_id = State()


@router.message(Command("companies"))
@router.message(Command("kompaniyalar"))
@router.message(F.text == "Kompaniyalar")
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
        await _safe_edit_text(callback.message, text, reply_markup=keyboard)
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
    await state.set_state(CompanyManagementStates.waiting_for_name)

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            "Kompaniya nomini yuboring.",
            reply_markup=build_company_cancel_keyboard(),
        )
    await callback.answer()


@router.message(CompanyManagementStates.waiting_for_name)
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
        await message.answer("Kompaniya nomi bo'sh bo'lishi mumkin emas. To'g'ri nom yuboring.")
        return

    await state.update_data(company_name=company_name)
    await state.set_state(CompanyManagementStates.waiting_for_plan)
    await message.answer(
        "Kompaniya tarifini tanlang.",
        reply_markup=build_company_plan_keyboard(),
    )


@router.callback_query(CompanyPlanCallback.filter(), CompanyManagementStates.waiting_for_plan)
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
            await _safe_edit_text(callback.message, text, reply_markup=keyboard)
        await callback.answer("Kompaniya nomi topilmadi. Qaytadan boshlang.", show_alert=True)
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
        await state.set_state(CompanyManagementStates.waiting_for_name)
        if callback.message is not None:
            await _safe_edit_text(
                callback.message,
                f"{exc}\n\nBoshqa kompaniya nomini yuboring.",
                reply_markup=build_company_cancel_keyboard(),
            )
        await callback.answer("Kompaniya nomi allaqachon mavjud.", show_alert=True)
        return

    await state.clear()
    if callback.message is not None:
        details_text = await _build_company_details_text(session, company)
        await _safe_edit_text(
            callback.message,
            "Kompaniya muvaffaqiyatli yaratildi.\n\n" + details_text,
            reply_markup=build_company_actions_keyboard(company.id),
        )
    await callback.answer("Kompaniya yaratildi.")


@router.message(CompanyManagementStates.waiting_for_plan)
async def waiting_for_plan_hint(
    message: Message,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_message(message, session)
    if admin is None:
        return

    await message.answer(
        "Tarifni tanlash uchun pastdagi inline tugmalardan foydalaning.",
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
        await callback.answer("Kompaniya topilmadi.", show_alert=True)
        return

    if callback.message is not None:
        details_text = await _build_company_details_text(session, company)
        await _safe_edit_text(
            callback.message,
            details_text,
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
        details_text = await _build_company_details_text(session, company)
        await _safe_edit_text(
            callback.message,
            "Obuna 30 kunga aktiv qilindi.\n\n" + details_text,
            reply_markup=build_company_actions_keyboard(company.id),
        )
    await callback.answer("Obuna aktiv qilindi.")


@router.callback_query(CompanyActionCallback.filter(F.action == "deactivate"))
async def deactivate_company_subscription(
    callback: CallbackQuery,
    callback_data: CompanyActionCallback,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_callback(callback, session)
    if admin is None:
        return

    company_service = CompanyService(session)
    try:
        company = await company_service.deactivate_subscription(callback_data.company_id)
    except CompanyNotFoundError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if callback.message is not None:
        details_text = await _build_company_details_text(session, company)
        await _safe_edit_text(
            callback.message,
            "Obuna qo‘lda bekor qilindi.\n\n" + details_text,
            reply_markup=build_company_actions_keyboard(company.id),
        )
    await callback.answer("Obuna bekor qilindi.")


@router.callback_query(CompanyActionCallback.filter(F.action == "bind_user"))
async def start_bind_user_to_company(
    callback: CallbackQuery,
    callback_data: CompanyActionCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_callback(callback, session)
    if admin is None:
        return

    company_service = CompanyService(session)
    company = await company_service.get_company(callback_data.company_id)
    if company is None:
        await callback.answer("Kompaniya topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.set_state(CompanyManagementStates.waiting_for_user_telegram_id)
    await state.update_data(company_id=company.id)

    if callback.message is not None:
        details_text = await _build_company_details_text(session, company)
        await _safe_edit_text(
            callback.message,
            details_text
            + "\n\nBiriktirmoqchi bo'lgan foydalanuvchining Telegram ID raqamini yuboring.",
            reply_markup=build_company_cancel_keyboard(),
        )
    await callback.answer()


@router.message(CompanyManagementStates.waiting_for_user_telegram_id)
async def bind_user_to_company(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    admin = await _authorize_super_admin_message(message, session)
    if admin is None:
        return

    telegram_id_text = (message.text or "").strip()
    if not telegram_id_text.isdigit():
        await message.answer("Telegram ID faqat raqamlardan iborat bo'lishi kerak.")
        return

    data = await state.get_data()
    company_id = int(data.get("company_id", 0))
    if company_id <= 0:
        await state.clear()
        await message.answer("Kompaniya ma'lumoti topilmadi. Qaytadan urinib ko'ring.")
        return

    company_service = CompanyService(session)
    company = await company_service.get_company(company_id)
    if company is None:
        await state.clear()
        await message.answer("Kompaniya topilmadi.")
        return

    user_service = UserService(session)
    try:
        user = await user_service.assign_company(int(telegram_id_text), company.id)
    except (UserNotFoundError, UserRoleChangeError) as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    details_text = await _build_company_details_text(session, company)
    await message.answer(
        f"Foydalanuvchi <b>{escape(user.display_name)}</b> kompaniyaga biriktirildi.\n\n"
        + details_text,
        reply_markup=build_company_actions_keyboard(company.id),
    )


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
        await callback.answer("Kompaniya topilmadi.", show_alert=True)
        return

    text, keyboard = await _build_company_list_view(session)
    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            "Kompaniya o'chirildi.\n\n" + text,
            reply_markup=keyboard,
        )
    await callback.answer("Kompaniya o'chirildi.")


async def _build_company_list_view(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    company_service = CompanyService(session)
    companies = await company_service.list_companies()
    user_service = UserService(session)
    management_summary = await user_service.get_management_users_by_company_ids(
        [company.id for company in companies]
    )

    lines = ["<b>Kompaniyalar boshqaruvi</b>", ""]
    if not companies:
        lines.append("Hali kompaniyalar yaratilmagan.")
    else:
        lines.append("Kompaniyalar ro'yxati:")
        lines.append("")
        for company in companies:
            status = _format_status(company)
            managers = management_summary.get(company.id, {})
            admin_count = len(managers.get(UserRole.ADMIN, []))
            operator_count = len(managers.get(UserRole.OPERATOR, []))
            lines.append(
                f"{company.id}. <b>{escape(company.name)}</b> | {_format_plan(company.plan)} | {status}"
            )
            lines.append(
                f"Adminlar: <b>{admin_count}</b> | Operatorlar: <b>{operator_count}</b>"
            )
            lines.append("")

    return "\n".join(lines).strip(), build_company_list_keyboard(companies)


async def _authorize_super_admin_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user is None or not user.is_super_admin:
        await message.answer("Kompaniyalarni faqat super admin boshqara oladi.")
        return None
    return user


async def _authorize_super_admin_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return None

    user = await _register_and_get_user(callback.from_user, session)
    if user is None or not user.is_super_admin:
        await callback.answer("Kompaniyalarni faqat super admin boshqara oladi.", show_alert=True)
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


async def _build_company_details_text(session: AsyncSession, company: Company) -> str:
    user_service = UserService(session)
    users = await user_service.get_users_by_company(company.id)
    admin_lines = [_format_user_reference(user) for user in users if user.role == UserRole.ADMIN]
    operator_lines = [_format_user_reference(user) for user in users if user.role == UserRole.OPERATOR]
    user_count = len([user for user in users if user.role == UserRole.USER])

    lines = [_format_company_details(company), "", "<b>Biriktirilgan foydalanuvchilar</b>"]
    lines.append("Adminlar: " + (", ".join(admin_lines) if admin_lines else "yo'q"))
    lines.append("Operatorlar: " + (", ".join(operator_lines) if operator_lines else "yo'q"))
    lines.append(f"Oddiy foydalanuvchilar: <b>{user_count}</b>")
    return "\n".join(lines)


def _format_company_details(company: Company) -> str:
    access_text = "✅ Ruxsat berilgan" if company.is_active else "❌ Bloklangan"
    return (
        f"<b>Kompaniya #{company.id}</b>\n"
        f"Nomi: <b>{escape(company.name)}</b>\n"
        f"Tarifi: <b>{_format_plan(company.plan)}</b>\n"
        f"Holati: <b>{_format_status(company)}</b>\n"
        f"Obuna muddati: <b>{_format_subscription_end(company.subscription_end)}</b>\n"
        f"Kirish: <b>{access_text}</b>"
    )


def _format_subscription_end(subscription_end: datetime | None) -> str:
    normalized = normalize_utc_datetime(subscription_end)
    if normalized is None:
        return "Faollashtirilmagan"

    return normalized.strftime("%Y-%m-%d %H:%M UTC")


def _format_plan(plan: CompanyPlan) -> str:
    if plan == CompanyPlan.PREMIUM:
        return "⭐ Premium"
    return "🆓 Bepul"


def _format_status(company: Company) -> str:
    return "🟢 Faol" if company.is_active else "🔴 Nofaol"


def _format_user_reference(user: User) -> str:
    return f"<b>{escape(user.display_name)}</b> ({user.telegram_id})"


async def _safe_edit_text(
    message: Message,
    text: str,
    reply_markup=None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
