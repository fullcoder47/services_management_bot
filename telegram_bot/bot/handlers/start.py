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
    UserLanguageCallback,
    build_company_choice_keyboard,
    build_language_select_keyboard,
    build_user_phone_keyboard,
)
from bot.states import StartStates
from db.models import Company, User, UserLanguage, UserRole
from services.company_service import CompanyService
from services.i18n import t
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
    user = registration.user

    if user.preferred_language is None:
        await state.set_state(StartStates.waiting_for_language)
        await state.update_data(start_created=registration.created)
        await message.answer(
            t(UserLanguage.UZ, "lang_select_title"),
            reply_markup=build_language_select_keyboard(),
        )
        return

    if not user.phone_number:
        await state.set_state(StartStates.waiting_for_phone)
        await state.update_data(start_created=registration.created)
        await message.answer(
            t(user.ui_language, "start_phone_prompt"),
            reply_markup=build_user_phone_keyboard(user.ui_language),
        )
        return

    await _show_start_view(
        message=message,
        user=user,
        created=registration.created,
        session=session,
    )


@router.callback_query(UserLanguageCallback.filter())
async def select_language(
    callback: CallbackQuery,
    callback_data: UserLanguageCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return

    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(callback.from_user)
    )

    language = UserLanguage(callback_data.language)
    user = await user_service.update_preferred_language(callback.from_user.id, language)
    data = await state.get_data()
    created = bool(data.get("start_created", registration.created))

    if not user.phone_number:
        await state.set_state(StartStates.waiting_for_phone)
        await state.update_data(start_created=created)
        if callback.message is not None:
            await _safe_edit_text(callback.message, t(language, "lang_saved"))
            await callback.message.answer(
                t(language, "start_phone_prompt"),
                reply_markup=build_user_phone_keyboard(language),
            )
        await callback.answer()
        return

    await state.clear()
    if callback.message is not None:
        await _safe_edit_text(callback.message, t(language, "lang_saved"))
        await _show_start_view(
            message=callback.message,
            user=user,
            created=created,
            session=session,
        )
    await callback.answer()


@router.message(StartStates.waiting_for_phone)
async def capture_user_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return

    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(message.from_user)
    )
    user = registration.user
    language = user.ui_language

    if not _is_valid_contact_owner(message):
        await message.answer(
            t(language, "start_phone_owner_only"),
            reply_markup=build_user_phone_keyboard(language),
        )
        return

    phone = _extract_phone(message)
    if not phone:
        await message.answer(
            t(language, "start_phone_invalid"),
            reply_markup=build_user_phone_keyboard(language),
        )
        return

    try:
        user = await user_service.update_phone_number(message.from_user.id, phone)
    except (UserNotFoundError, UserValidationError) as exc:
        await message.answer(str(exc), reply_markup=build_user_phone_keyboard(language))
        return

    data = await state.get_data()
    created = bool(data.get("start_created", registration.created))
    await state.clear()
    await message.answer(
        t(language, "start_phone_saved"),
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
    language = user.ui_language

    if not user.phone_number:
        await callback.answer(t(language, "start_need_phone_first"), show_alert=True)
        return

    company_service = CompanyService(session)
    company = await company_service.get_company(callback_data.company_id)
    if company is None or not company_service.check_access(company):
        await callback.answer(t(language, "start_company_inactive"), show_alert=True)
        return

    try:
        user = await user_service.select_company_for_user(user.telegram_id, company.id)
    except (UserNotFoundError, UserRoleChangeError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            t(language, "start_company_selected", company=escape(company.name)),
        )
        await callback.message.answer(
            _build_user_text(user, company, registration.created),
            reply_markup=build_main_menu(role=user.role, has_company=True, language=language),
        )

    await callback.answer()


async def _show_start_view(
    message: Message,
    user: User,
    created: bool,
    session: AsyncSession,
) -> None:
    company_service = CompanyService(session)
    company = await _resolve_user_company(user, company_service)
    language = user.ui_language

    if user.is_super_admin:
        await message.answer(
            _build_super_admin_text(user, created),
            reply_markup=build_main_menu(role=user.role, has_company=False, language=language),
        )
        return

    if user.role in {UserRole.ADMIN, UserRole.OPERATOR}:
        if company is None:
            await message.answer(
                t(language, "manager_no_company"),
                reply_markup=build_main_menu(role=user.role, has_company=False, language=language),
            )
            return

        await message.answer(
            _build_manager_text(user, company, created),
            reply_markup=build_main_menu(role=user.role, has_company=True, language=language),
        )
        return

    if company is None:
        text, keyboard = await _build_company_selection_view(company_service, language)
        await message.answer(text, reply_markup=keyboard)
        return

    await message.answer(
        _build_user_text(user, company, created),
        reply_markup=build_main_menu(role=user.role, has_company=True, language=language),
    )


async def _build_company_selection_view(
    company_service: CompanyService,
    language: UserLanguage,
) -> tuple[str, object | None]:
    companies = await company_service.list_active_companies()
    if not companies:
        return t(language, "start_no_companies"), None
    return t(language, "start_choose_company"), build_company_choice_keyboard(companies)


async def _resolve_user_company(
    user: User,
    company_service: CompanyService,
) -> Company | None:
    if user.company_id is None:
        return None
    return await company_service.get_active_company(user.company_id)


def _build_super_admin_text(user: User, created: bool) -> str:
    language = user.ui_language
    created_text = t(language, "registered_new") if created else t(language, "registered_existing")
    return t(
        language,
        "welcome_super_admin",
        name=escape(user.display_name),
        phone=escape(user.phone_number or "-"),
        created_text=created_text,
    )


def _build_manager_text(user: User, company: Company, created: bool) -> str:
    language = user.ui_language
    created_text = t(language, "registered_new") if created else t(language, "registered_existing")
    role_key = "role_admin" if user.role == UserRole.ADMIN else "role_operator"
    return t(
        language,
        "welcome_manager",
        name=escape(user.display_name),
        role=t(language, role_key),
        company=escape(company.name),
        phone=escape(user.phone_number or "-"),
        created_text=created_text,
    )


def _build_user_text(user: User, company: Company, created: bool) -> str:
    language = user.ui_language
    created_text = t(language, "registered_new") if created else t(language, "registered_existing")
    return t(
        language,
        "welcome_user",
        name=escape(user.display_name),
        company=escape(company.name),
        phone=escape(user.phone_number or "-"),
        created_text=created_text,
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
