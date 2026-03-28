from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import build_main_menu
from bot.keyboards.user_keyboard import (
    UserCompanySelectCallback,
    build_company_choice_keyboard,
    build_user_phone_keyboard,
)
from bot.states import StartStates
from db.models import Company, User, UserRole
from services.company_service import CompanyService
from services.user_service import (
    TelegramUserDTO,
    UserNotFoundError,
    UserRoleChangeError,
    UserService,
    UserValidationError,
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

    if not registration.user.phone_number:
        await state.set_state(StartStates.waiting_for_phone)
        await state.update_data(start_created=registration.created)
        await message.answer(
            "Botdan foydalanish uchun telefon raqamingizni yuboring yoki pastdagi tugma orqali ulashing.",
            reply_markup=build_user_phone_keyboard(),
        )
        return

    await _show_start_view(
        message=message,
        user=registration.user,
        created=registration.created,
        session=session,
    )


@router.message(StartStates.waiting_for_phone)
async def capture_user_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return

    if not _is_valid_contact_owner(message):
        await message.answer(
            "Iltimos, faqat o'zingizning telefon raqamingizni yuboring.",
            reply_markup=build_user_phone_keyboard(),
        )
        return

    phone = _extract_phone(message)
    if not phone:
        await message.answer(
            "Telefon raqami majburiy. Uni yozib yuboring yoki pastdagi tugma bilan ulashing.",
            reply_markup=build_user_phone_keyboard(),
        )
        return

    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(message.from_user)
    )

    try:
        user = await user_service.update_phone_number(message.from_user.id, phone)
    except (UserNotFoundError, UserValidationError) as exc:
        await message.answer(str(exc), reply_markup=build_user_phone_keyboard())
        return

    data = await state.get_data()
    created = bool(data.get("start_created", registration.created))
    await state.clear()

    await message.answer(
        "Telefon raqamingiz muvaffaqiyatli saqlandi.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _show_start_view(
        message=message,
        user=user,
        created=created,
        session=session,
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

    if not user.phone_number:
        await callback.answer("Avval /start yuborib telefon raqamingizni saqlang.", show_alert=True)
        return

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


async def _show_start_view(
    message: Message,
    user: User,
    created: bool,
    session: AsyncSession,
) -> None:
    company_service = CompanyService(session)
    company = await _resolve_user_company(user, company_service)

    if user.is_super_admin:
        await message.answer(
            _build_super_admin_text(user, created),
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
            _build_manager_text(user, company, created),
            reply_markup=build_main_menu(role=user.role, has_company=True),
        )
        return

    if company is None:
        text, keyboard = await _build_company_selection_view(company_service)
        await message.answer(text, reply_markup=keyboard)
        return

    await message.answer(
        _build_user_text(user, company, created),
        reply_markup=build_main_menu(role=user.role, has_company=True),
    )


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
        f"Telefon: <b>{escape(user.phone_number or '-')}</b>\n"
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
        f"Telefon: <b>{escape(user.phone_number or '-')}</b>.\n"
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
        f"Telefon: <b>{escape(user.phone_number or '-')}</b>.\n"
        f"{created_text}\n\n"
        "📨 Ariza qoldirish yoki 📄 Mening arizalarim bo‘limidan foydalanishingiz mumkin."
    )


def _extract_phone(message: Message) -> str:
    if message.contact is not None and message.contact.phone_number:
        return message.contact.phone_number.strip()
    if message.text is not None:
        return message.text.strip()
    return ""


def _is_valid_contact_owner(message: Message) -> bool:
    if message.contact is None or message.from_user is None:
        return True
    if message.contact.user_id is None:
        return True
    return message.contact.user_id == message.from_user.id


async def _safe_edit_text(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
