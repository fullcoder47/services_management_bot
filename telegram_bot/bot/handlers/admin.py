from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin_keyboard import (
    AdminCompanyCallback,
    AdminConfirmCallback,
    AdminMenuCallback,
    AdminRoleCallback,
    build_admin_company_select_keyboard,
    build_admin_confirm_keyboard,
    build_admin_role_select_keyboard,
)
from bot.states import AdminAssignStates
from db.models import Company, User, UserRole
from services.company_service import CompanyService
from services.user_service import (
    TelegramUserDTO,
    UserRoleChangeError,
    UserService,
)


router = Router(name=__name__)


@router.message(Command("admins"))
@router.message(F.text == "👤 Adminlar")
async def admin_panel_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_super_admin_message(message, session)
    if current_user is None:
        return

    await _show_admin_panel_message(message, state, session)


@router.callback_query(AdminMenuCallback.filter(F.action == "cancel"))
async def admin_panel_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_super_admin_callback(callback, session)
    if current_user is None:
        return

    await _show_admin_panel_callback(callback, state, session)
    await callback.answer()


@router.callback_query(AdminCompanyCallback.filter(), AdminAssignStates.waiting_for_company)
async def admin_select_company(
    callback: CallbackQuery,
    callback_data: AdminCompanyCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_super_admin_callback(callback, session)
    if current_user is None:
        return

    company_service = CompanyService(session)
    company = await company_service.get_company(callback_data.company_id)
    if company is None:
        await callback.answer("Kompaniya topilmadi.", show_alert=True)
        return

    await state.set_state(AdminAssignStates.waiting_for_user_id)
    await state.update_data(company_id=company.id, company_name=company.name)

    if callback.message is not None:
        await callback.message.edit_text(
            f"👤 Admin boshqaruvi\n\nKompaniya: <b>{company.name}</b>\n\nTelegram user ID yuboring",
        )
    await callback.answer()


@router.message(AdminAssignStates.waiting_for_user_id)
async def admin_capture_user_id(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_super_admin_message(message, session)
    if current_user is None:
        return

    user_id_text = (message.text or "").strip()
    if not user_id_text.isdigit():
        await message.answer("Telegram user ID noto‘g‘ri. Faqat raqam kiriting.")
        return

    await state.update_data(user_id=int(user_id_text))
    await state.set_state(AdminAssignStates.waiting_for_role)
    await message.answer(
        "Rolni tanlang",
        reply_markup=build_admin_role_select_keyboard(),
    )


@router.callback_query(AdminRoleCallback.filter(), AdminAssignStates.waiting_for_role)
async def admin_select_role(
    callback: CallbackQuery,
    callback_data: AdminRoleCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_super_admin_callback(callback, session)
    if current_user is None:
        return

    role = _parse_assign_role(callback_data.role)
    if role is None:
        await callback.answer("Rol noto‘g‘ri.", show_alert=True)
        return

    data = await state.get_data()
    company_name = str(data.get("company_name", ""))
    user_id = data.get("user_id")
    if not isinstance(user_id, int):
        await callback.answer("Foydalanuvchi ID topilmadi. Qaytadan boshlang.", show_alert=True)
        return

    await state.update_data(role=role.value)

    if callback.message is not None:
        await callback.message.edit_text(
            "Tasdiqlang:\n\n"
            f"Kompaniya: <b>{company_name}</b>\n"
            f"ID: <b>{user_id}</b>\n"
            f"Rol: <b>{role.value}</b>",
            reply_markup=build_admin_confirm_keyboard(),
        )
    await callback.answer()


@router.callback_query(AdminConfirmCallback.filter(F.action == "confirm"), AdminAssignStates.waiting_for_role)
async def admin_confirm_assign(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_super_admin_callback(callback, session)
    if current_user is None:
        return

    data = await state.get_data()
    company_id = data.get("company_id")
    user_id = data.get("user_id")
    role_value = data.get("role")

    if not isinstance(company_id, int) or not isinstance(user_id, int) or not isinstance(role_value, str):
        await state.clear()
        await callback.answer("Ma'lumotlar topilmadi. Qaytadan boshlang.", show_alert=True)
        return

    role = _parse_assign_role(role_value)
    if role is None:
        await state.clear()
        await callback.answer("Rol noto‘g‘ri.", show_alert=True)
        return

    company_service = CompanyService(session)
    company = await company_service.get_company(company_id)
    if company is None:
        await state.clear()
        await callback.answer("Kompaniya topilmadi.", show_alert=True)
        return

    user_service = UserService(session)
    try:
        user = await user_service.assign_user_to_company(user_id, company.id, role)
    except UserRoleChangeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.set_state(AdminAssignStates.waiting_for_company)
    companies = await company_service.list_companies()

    result_text = (
        "✅ User muvaffaqiyatli qo‘shildi:\n"
        f"ID: <b>{user.telegram_id}</b>\n"
        f"Role: <b>{user.role.value}</b>\n"
        f"Company: <b>{company.name}</b>"
    )

    if callback.message is not None:
        await callback.message.edit_text(
            result_text + "\n\nKompaniyani tanlang",
            reply_markup=build_admin_company_select_keyboard(companies),
        )
    await callback.answer()


@router.callback_query(AdminConfirmCallback.filter(F.action == "cancel"), AdminAssignStates.waiting_for_role)
async def admin_cancel_assign(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_super_admin_callback(callback, session)
    if current_user is None:
        return

    await _show_admin_panel_callback(callback, state, session)
    await callback.answer()


async def _show_admin_panel_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.clear()
    await state.set_state(AdminAssignStates.waiting_for_company)

    company_service = CompanyService(session)
    companies = await company_service.list_companies()
    if not companies:
        await message.answer("👤 Admin boshqaruvi\n\nHali kompaniyalar mavjud emas.")
        return

    await message.answer(
        "👤 Admin boshqaruvi\n\nKompaniyani tanlang",
        reply_markup=build_admin_company_select_keyboard(companies),
    )


async def _show_admin_panel_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.clear()
    await state.set_state(AdminAssignStates.waiting_for_company)

    company_service = CompanyService(session)
    companies = await company_service.list_companies()
    text = "👤 Admin boshqaruvi\n\nKompaniyani tanlang"
    if not companies:
        text = "👤 Admin boshqaruvi\n\nHali kompaniyalar mavjud emas."

    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=build_admin_company_select_keyboard(companies) if companies else None,
        )


async def _authorize_super_admin_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo‘lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user is None or user.role != UserRole.SUPER_ADMIN:
        await message.answer("Bu bo‘limga faqat super admin kira oladi.")
        return None
    return user


async def _authorize_super_admin_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo‘lmadi.", show_alert=True)
        return None

    user = await _register_and_get_user(callback.from_user, session)
    if user is None or user.role != UserRole.SUPER_ADMIN:
        await callback.answer("Bu bo‘limga faqat super admin kira oladi.", show_alert=True)
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


def _parse_assign_role(role_value: str) -> UserRole | None:
    if role_value == UserRole.ADMIN.value:
        return UserRole.ADMIN
    if role_value == UserRole.OPERATOR.value:
        return UserRole.OPERATOR
    return None
