from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import build_main_menu
from bot.keyboards.user_keyboard import UserCompanySelectCallback, build_company_choice_keyboard
from db.models import Company, User, UserRole
from services.company_service import CompanyService
from services.user_service import (
    TelegramUserDTO,
    UserNotFoundError,
    UserRoleChangeError,
    UserService,
)


router = Router(name=__name__)


@router.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return

    await state.clear()
    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(message.from_user)
    )
    user = registration.user

    company_service = CompanyService(session)
    company = await _resolve_user_company(user, company_service)

    if user.is_super_admin:
        await message.answer(
            _build_super_admin_text(user, registration.created),
            reply_markup=build_main_menu(role=user.role, has_company=False),
        )
        return

    if user.role in {UserRole.ADMIN, UserRole.OPERATOR}:
        if company is None:
            await message.answer(
                "Siz hali kompaniyaga biriktirilmagansiz. Super admin bilan bog'laning.",
                reply_markup=build_main_menu(role=user.role, has_company=False),
            )
            return

        await message.answer(
            _build_manager_text(user, company, registration.created),
            reply_markup=build_main_menu(role=user.role, has_company=True),
        )
        return

    if company is None:
        text, keyboard = await _build_company_selection_view(company_service)
        await message.answer(
            text,
            reply_markup=keyboard,
        )
        return

    await message.answer(
        _build_user_text(user, company, registration.created),
        reply_markup=build_main_menu(role=user.role, has_company=True),
    )


@router.callback_query(UserCompanySelectCallback.filter())
async def user_company_select(
    callback: CallbackQuery,
    callback_data: UserCompanySelectCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return

    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(callback.from_user)
    )
    user = registration.user

    company_service = CompanyService(session)
    company = await company_service.get_company(callback_data.company_id)
    if company is None or not company_service.check_access(company):
        await callback.answer("❌ Bu kompaniya vaqtincha faol emas.", show_alert=True)
        return

    try:
        user = await user_service.select_company_for_user(user.telegram_id, company.id)
    except (UserNotFoundError, UserRoleChangeError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            f"✅ Siz <b>{escape(company.name)}</b> kompaniyasini tanladingiz.",
        )
        await callback.message.answer(
            _build_user_text(user, company, registration.created),
            reply_markup=build_main_menu(role=user.role, has_company=True),
        )

    await callback.answer("Kompaniya tanlandi.")


async def _build_company_selection_view(
    company_service: CompanyService,
) -> tuple[str, object | None]:
    companies = await company_service.list_active_companies()
    if not companies:
        return (
            "🏢 O‘z kompaniyangizni tanlang\n\nHozircha faol kompaniyalar mavjud emas.",
            None,
        )

    return (
        "🏢 O‘z kompaniyangizni tanlang",
        build_company_choice_keyboard(companies),
    )


async def _resolve_user_company(
    user: User,
    company_service: CompanyService,
) -> Company | None:
    if user.company_id is None:
        return None
    return await company_service.get_active_company(user.company_id)


def _build_super_admin_text(user: User, created: bool) -> str:
    created_text = (
        "Siz botda muvaffaqiyatli ro'yxatdan o'tdingiz."
        if created
        else "Siz allaqachon ro'yxatdan o'tgansiz."
    )
    return (
        f"Salom, <b>{escape(user.display_name)}</b>!\n\n"
        "Sizning rolingiz: <b>super admin</b>.\n"
        f"{created_text}\n\n"
        "Kompaniyalarni boshqarish uchun <b>Kompaniyalar</b> tugmasidan foydalaning.\n"
        "Admin boshqaruvi uchun <b>👤 Adminlar</b> tugmasini bosing.\n"
        "Global requestlar va xabarlar uchun admin panel tugmalari ham mavjud."
    )


def _build_manager_text(user: User, company: Company, created: bool) -> str:
    created_text = (
        "Siz botda muvaffaqiyatli ro'yxatdan o'tdingiz."
        if created
        else "Siz allaqachon ro'yxatdan o'tgansiz."
    )
    role_text = "admin" if user.role == UserRole.ADMIN else "operator"
    return (
        f"Salom, <b>{escape(user.display_name)}</b>!\n\n"
        f"Sizning rolingiz: <b>{role_text}</b>.\n"
        f"Kompaniya: <b>{escape(company.name)}</b>.\n"
        f"{created_text}"
    )


def _build_user_text(user: User, company: Company, created: bool) -> str:
    created_text = (
        "Siz botda muvaffaqiyatli ro'yxatdan o'tdingiz."
        if created
        else "Xush kelibsiz."
    )
    return (
        f"Salom, <b>{escape(user.display_name)}</b>!\n\n"
        f"Kompaniya: <b>{escape(company.name)}</b>.\n"
        f"{created_text}\n\n"
        "📨 Ariza qoldirish yoki 📄 Mening arizalarim bo‘limidan foydalanishingiz mumkin."
    )


async def _safe_edit_text(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
