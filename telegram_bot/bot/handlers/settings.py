from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import build_main_menu
from bot.keyboards.settings_keyboard import (
    SettingsCompanyCallback,
    SettingsLanguageCallback,
    SettingsMenuCallback,
    build_settings_company_keyboard,
    build_settings_language_keyboard,
    build_settings_menu_keyboard,
)
from bot.keyboards.user_keyboard import build_user_phone_keyboard
from bot.states import SettingsStates
from db.models import Company, User, UserLanguage, UserRole
from services.company_service import CompanyService
from services.i18n import button_variants, t
from services.user_service import (
    TelegramUserDTO,
    UserNotFoundError,
    UserRoleChangeError,
    UserService,
    UserValidationError,
)


router = Router(name=__name__)


@router.message(Command("settings"))
@router.message(Command("sozlamalar"))
@router.message(F.text.in_(button_variants("menu_settings")))
async def settings_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await _register_and_get_user(message.from_user, session)
    if user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return

    await state.clear()
    await message.answer(
        await _build_settings_text(user, session),
        reply_markup=build_settings_menu_keyboard(
            user.ui_language,
            can_change_company=_can_change_company(user),
        ),
    )


@router.callback_query(SettingsMenuCallback.filter(F.action == "open"))
async def settings_open_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await _register_and_get_user(callback.from_user, session)
    if user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return

    await state.clear()
    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            await _build_settings_text(user, session),
            reply_markup=build_settings_menu_keyboard(
                user.ui_language,
                can_change_company=_can_change_company(user),
            ),
        )
    await callback.answer()


@router.callback_query(SettingsMenuCallback.filter(F.action == "language"))
async def settings_language_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    user = await _register_and_get_user(callback.from_user, session)
    if user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            t(user.ui_language, "settings_language_prompt"),
            reply_markup=build_settings_language_keyboard(user.ui_language),
        )
    await callback.answer()


@router.callback_query(SettingsLanguageCallback.filter())
async def settings_change_language(
    callback: CallbackQuery,
    callback_data: SettingsLanguageCallback,
    session: AsyncSession,
) -> None:
    user = await _register_and_get_user(callback.from_user, session)
    if user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return

    user_service = UserService(session)
    language = UserLanguage(callback_data.language)
    user = await user_service.update_preferred_language(user.telegram_id, language)

    if callback.message is not None:
        await callback.message.answer(
            t(user.ui_language, "settings_language_saved"),
            reply_markup=build_main_menu(
                role=user.role,
                has_company=user.company_id is not None,
                language=user.ui_language,
            ),
        )

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            await _build_settings_text(user, session),
            reply_markup=build_settings_menu_keyboard(
                user.ui_language,
                can_change_company=_can_change_company(user),
            ),
        )
    await callback.answer(t(user.ui_language, "settings_language_saved"))


@router.callback_query(SettingsMenuCallback.filter(F.action == "phone"))
async def settings_change_phone_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await _register_and_get_user(callback.from_user, session)
    if user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return

    await state.clear()
    await state.set_state(SettingsStates.waiting_for_phone)
    if callback.message is not None:
        await _safe_edit_text(callback.message, t(user.ui_language, "settings_phone_prompt"))
        await callback.message.answer(
            t(user.ui_language, "settings_phone_prompt"),
            reply_markup=build_user_phone_keyboard(user.ui_language),
        )
    await callback.answer()


@router.message(SettingsStates.waiting_for_phone)
async def settings_change_phone_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await _register_and_get_user(message.from_user, session)
    if user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return

    if not _is_valid_contact_owner(message):
        await message.answer(
            t(user.ui_language, "start_phone_owner_only"),
            reply_markup=build_user_phone_keyboard(user.ui_language),
        )
        return

    phone_number = _extract_phone(message)
    if not phone_number:
        await message.answer(
            t(user.ui_language, "start_phone_invalid"),
            reply_markup=build_user_phone_keyboard(user.ui_language),
        )
        return

    user_service = UserService(session)
    try:
        user = await user_service.update_phone_number(user.telegram_id, phone_number)
    except (UserNotFoundError, UserValidationError) as exc:
        await message.answer(str(exc), reply_markup=build_user_phone_keyboard(user.ui_language))
        return

    await state.clear()
    await message.answer(
        t(user.ui_language, "settings_phone_saved"),
        reply_markup=build_main_menu(
            role=user.role,
            has_company=user.company_id is not None,
            language=user.ui_language,
        ),
    )
    await message.answer(
        await _build_settings_text(user, session),
        reply_markup=build_settings_menu_keyboard(
            user.ui_language,
            can_change_company=_can_change_company(user),
        ),
    )


@router.callback_query(SettingsMenuCallback.filter(F.action == "company"))
async def settings_change_company_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    user = await _register_and_get_user(callback.from_user, session)
    if user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return

    if not _can_change_company(user):
        await callback.answer(t(user.ui_language, "settings_company_denied"), show_alert=True)
        return

    company_service = CompanyService(session)
    companies = await company_service.list_active_companies()
    if not companies:
        await callback.answer(t(user.ui_language, "settings_no_companies"), show_alert=True)
        return

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            t(user.ui_language, "settings_company_prompt"),
            reply_markup=build_settings_company_keyboard(companies, user.ui_language),
        )
    await callback.answer()


@router.callback_query(SettingsCompanyCallback.filter())
async def settings_change_company_finish(
    callback: CallbackQuery,
    callback_data: SettingsCompanyCallback,
    session: AsyncSession,
) -> None:
    user = await _register_and_get_user(callback.from_user, session)
    if user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return

    if not _can_change_company(user):
        await callback.answer(t(user.ui_language, "settings_company_denied"), show_alert=True)
        return

    company_service = CompanyService(session)
    company = await company_service.get_active_company(callback_data.company_id)
    if company is None:
        await callback.answer(t(user.ui_language, "settings_company_unavailable"), show_alert=True)
        return

    user_service = UserService(session)
    try:
        user = await user_service.select_company_for_user(user.telegram_id, company.id)
    except (UserNotFoundError, UserRoleChangeError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.answer(
            t(user.ui_language, "settings_company_saved", company=escape(company.name)),
            reply_markup=build_main_menu(
                role=user.role,
                has_company=True,
                language=user.ui_language,
            ),
        )

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            t(user.ui_language, "settings_company_saved", company=escape(company.name)),
            reply_markup=build_settings_menu_keyboard(
                user.ui_language,
                can_change_company=_can_change_company(user),
            ),
        )
    await callback.answer()


async def _build_settings_text(user: User, session: AsyncSession) -> str:
    company = await _resolve_company(user, session)
    language = user.ui_language
    company_name = company.name if company is not None else t(language, "settings_not_set")
    phone = user.phone_number or t(language, "settings_not_set")

    return "\n".join(
        [
            t(language, "settings_title"),
            "",
            t(language, "settings_role_line", role=_format_role(user.role, language)),
            t(language, "settings_phone_line", phone=escape(phone)),
            t(language, "settings_language_line", language_name=t(language, "lang_name")),
            t(language, "settings_company_line", company=escape(company_name)),
        ]
    )


async def _resolve_company(user: User, session: AsyncSession) -> Company | None:
    if user.company_id is None:
        return None
    company_service = CompanyService(session)
    return await company_service.get_company(user.company_id)


async def _register_and_get_user(
    telegram_user: AiogramUser | None,
    session: AsyncSession,
) -> User | None:
    if telegram_user is None:
        return None
    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(telegram_user)
    )
    return registration.user


def _can_change_company(user: User) -> bool:
    return user.role == UserRole.USER


def _format_role(role: UserRole, language: UserLanguage) -> str:
    if role == UserRole.SUPER_ADMIN:
        return t(language, "role_super_admin")
    if role == UserRole.ADMIN:
        return t(language, "role_admin")
    if role == UserRole.OPERATOR:
        return t(language, "role_operator")
    if role == UserRole.WORKER:
        return t(language, "role_worker")
    return t(language, "role_user")


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


async def _safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        await message.answer(text, reply_markup=reply_markup)
