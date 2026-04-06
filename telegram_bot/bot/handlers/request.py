from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import build_main_menu
from bot.keyboards.request_keyboard import (
    RequestMenuCallback,
    build_request_create_cancel_keyboard,
    build_request_optional_image_keyboard,
)
from bot.keyboards.user_keyboard import (
    UserRequestMenuCallback,
    UserRequestSelectCallback,
    build_user_request_back_keyboard,
    build_user_request_list_keyboard,
)
from bot.states import RequestCreateStates
from db.models import Request, RequestStatus, User, UserRole
from services.i18n import button_variants, t
from services.request_service import (
    CreateRequestDTO,
    RequestAccessDeniedError,
    RequestNotFoundError,
    RequestService,
    RequestValidationError,
)
from services.translation_service import TranslationService
from services.user_service import TelegramUserDTO, UserService


router = Router(name=__name__)


@router.message(Command("request"))
@router.message(F.text.in_(button_variants("menu_leave_request")))
async def request_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    language = current_user.ui_language
    if not current_user.phone_number:
        await message.answer(t(language, "start_need_phone_first"))
        return

    await state.clear()
    await state.set_state(RequestCreateStates.waiting_for_problem)
    await message.answer(
        t(language, "request_problem_prompt"),
        reply_markup=build_request_create_cancel_keyboard(language),
    )


@router.message(Command("my_requests"))
@router.message(F.text.in_(button_variants("menu_my_requests")))
async def my_requests_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    await state.clear()
    text, keyboard = await _build_user_requests_view(session, current_user)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(
    RequestMenuCallback.filter(F.action == "cancel_create"),
    RequestCreateStates.waiting_for_problem,
)
@router.callback_query(
    RequestMenuCallback.filter(F.action == "cancel_create"),
    RequestCreateStates.waiting_for_address,
)
@router.callback_query(
    RequestMenuCallback.filter(F.action == "cancel_create"),
    RequestCreateStates.waiting_for_image,
)
async def request_create_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_callback(callback, session)
    if current_user is None:
        return

    language = current_user.ui_language
    await state.clear()
    if callback.message is not None:
        await _safe_edit_text(callback.message, t(language, "request_cancelled"))
        await callback.message.answer(
            t(language, "request_menu_title"),
            reply_markup=_build_user_menu(current_user),
        )
    await callback.answer()


@router.callback_query(
    RequestMenuCallback.filter(F.action == "skip_image"),
    RequestCreateStates.waiting_for_image,
)
async def request_create_skip_image(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_callback(callback, session)
    if current_user is None:
        return

    language = current_user.ui_language
    try:
        request = await _create_request_from_state(
            state=state,
            session=session,
            current_user=current_user,
            problem_image=None,
        )
    except RequestValidationError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            t(language, "request_created", request_id=request.id),
        )
        await callback.message.answer(
            t(language, "request_menu_title"),
            reply_markup=_build_user_menu(current_user),
        )
    await callback.answer()
    await _notify_management_users(callback.bot, session, request)


@router.callback_query(UserRequestMenuCallback.filter(F.action == "list"))
async def user_requests_list_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_callback(callback, session)
    if current_user is None:
        return

    text, keyboard = await _build_user_requests_view(session, current_user)
    if callback.message is not None:
        await _safe_edit_text(callback.message, text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(UserRequestSelectCallback.filter())
async def user_request_detail_callback(
    callback: CallbackQuery,
    callback_data: UserRequestSelectCallback,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_callback(callback, session)
    if current_user is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_for_user(callback_data.request_id, current_user)
    except (RequestAccessDeniedError, RequestNotFoundError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            _format_user_request_detail(request, current_user.ui_language),
            reply_markup=build_user_request_back_keyboard(current_user.ui_language),
        )
    await callback.answer()


@router.message(RequestCreateStates.waiting_for_problem)
async def capture_request_problem(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    language = current_user.ui_language
    problem_text = (message.text or "").strip()
    if not problem_text:
        await message.answer(
            t(language, "request_problem_required"),
            reply_markup=build_request_create_cancel_keyboard(language),
        )
        return

    await state.update_data(problem_text=problem_text)
    await state.set_state(RequestCreateStates.waiting_for_address)
    await message.answer(
        t(language, "request_address_prompt"),
        reply_markup=build_request_create_cancel_keyboard(language),
    )


@router.message(RequestCreateStates.waiting_for_address)
async def capture_request_address(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    language = current_user.ui_language
    address = (message.text or "").strip()
    if not address:
        await message.answer(
            t(language, "request_address_required"),
            reply_markup=build_request_create_cancel_keyboard(language),
        )
        return

    await state.update_data(address=address)
    await state.set_state(RequestCreateStates.waiting_for_image)
    await message.answer(
        t(language, "request_image_prompt"),
        reply_markup=build_request_optional_image_keyboard(language),
    )


@router.message(RequestCreateStates.waiting_for_image, F.photo)
async def capture_request_image(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    language = current_user.ui_language
    photo = message.photo[-1]
    try:
        request = await _create_request_from_state(
            state=state,
            session=session,
            current_user=current_user,
            problem_image=photo.file_id,
        )
    except RequestValidationError as exc:
        await message.answer(str(exc), reply_markup=build_request_optional_image_keyboard(language))
        return

    await state.clear()
    await message.answer(
        t(language, "request_created_with_image", request_id=request.id),
        reply_markup=_build_user_menu(current_user),
    )
    await _notify_management_users(message.bot, session, request)


@router.message(RequestCreateStates.waiting_for_image)
async def capture_request_image_invalid(
    message: Message,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    await message.answer(
        t(current_user.ui_language, "request_image_invalid"),
        reply_markup=build_request_optional_image_keyboard(current_user.ui_language),
    )


async def _create_request_from_state(
    state: FSMContext,
    session: AsyncSession,
    current_user: User,
    problem_image: str | None,
) -> Request:
    if current_user.company_id is None:
        raise RequestValidationError(t(current_user.ui_language, "start_choose_company"))
    if not current_user.phone_number:
        raise RequestValidationError(t(current_user.ui_language, "start_need_phone_first"))

    data = await state.get_data()
    problem_text = str(data.get("problem_text", "")).strip()
    address = str(data.get("address", "")).strip()

    request_service = RequestService(session)
    return await request_service.create_request(
        CreateRequestDTO(
            user_id=current_user.id,
            company_id=current_user.company_id,
            phone=current_user.phone_number,
            problem_text=problem_text,
            address=address,
            problem_image=problem_image,
        )
    )


async def _build_user_requests_view(
    session: AsyncSession,
    user: User,
) -> tuple[str, object | None]:
    request_service = RequestService(session)
    requests = await request_service.list_user_requests(user.id)
    language = user.ui_language

    lines = [t(language, "request_list_title"), ""]
    if not requests:
        lines.append(t(language, "request_list_empty"))
        return "\n".join(lines), None

    lines.append(t(language, "request_list_items"))
    lines.append("")
    for request in requests:
        lines.append(f"#{request.id} | {RequestService.format_status(request.status, language)}")

    return "\n".join(lines), build_user_request_list_keyboard(requests, language)


async def _notify_management_users(
    bot: Bot,
    session: AsyncSession,
    request: Request,
) -> None:
    if request.company_id is None:
        return

    request_service = RequestService(session)
    recipients = await request_service.get_management_recipients(request.company_id)
    if not recipients:
        return

    request = await request_service.get_request_or_raise(request.id)
    translator = TranslationService()

    from bot.keyboards.request_keyboard import build_request_admin_actions_keyboard

    for recipient in recipients:
        try:
            text = await _format_admin_new_request_text(request, recipient.ui_language, translator)
            if request.problem_image:
                await bot.send_photo(
                    chat_id=recipient.telegram_id,
                    photo=request.problem_image,
                    caption=text,
                    reply_markup=build_request_admin_actions_keyboard(request, recipient.ui_language),
                )
            else:
                await bot.send_message(
                    chat_id=recipient.telegram_id,
                    text=text,
                    reply_markup=build_request_admin_actions_keyboard(request, recipient.ui_language),
                )
        except Exception:
            continue


async def _format_admin_new_request_text(
    request: Request,
    language,
    translator: TranslationService,
) -> str:
    user_name = request.user.display_name if request.user is not None else "Unknown"
    company_name = request.company.name if request.company is not None else "Unknown company"
    translated_problem = await translator.translate_text(request.problem_text, language)
    translated_address = await translator.translate_text(request.address, language)
    return (
        f"{t(language, 'request_new_title')}\n"
        f"{t(language, 'request_new_company')}: <b>{escape(company_name)}</b>\n"
        f"{t(language, 'request_new_user')}: <b>{escape(user_name)}</b>\n"
        f"{t(language, 'request_new_phone')}: <b>{escape(request.phone)}</b>\n"
        f"{t(language, 'request_new_problem')}: <b>{escape(translated_problem)}</b>\n"
        f"{t(language, 'request_new_address')}: <b>{escape(translated_address)}</b>"
    )


def _format_user_request_detail(request: Request, language) -> str:
    completed_by_worker = request.completed_by_worker.display_name if request.completed_by_worker is not None else ""
    lines = [
        f"<b>{t(language, 'request_detail_title', request_id=request.id)}</b>",
        f"{t(language, 'request_detail_status')}: <b>{RequestService.format_status(request.status, language)}</b>",
        f"{t(language, 'request_detail_phone')}: <b>{escape(request.phone)}</b>",
        f"{t(language, 'request_detail_problem')}: <b>{escape(request.problem_text)}</b>",
        f"{t(language, 'request_detail_address')}: <b>{escape(request.address)}</b>",
    ]
    if request.problem_image:
        lines.append(t(language, "request_detail_image"))
    if request.status == RequestStatus.DONE:
        lines.append(f"{t(language, 'request_detail_done_note')}: <b>{escape(request.result_text or '')}</b>")
        if completed_by_worker:
            lines.append(
                f"{t(language, 'request_detail_completed_by_worker')}: <b>{escape(completed_by_worker)}</b>"
            )
        if request.completed_at is not None:
            lines.append(
                f"{t(language, 'request_detail_done_at')}: <b>{request.completed_at.strftime('%Y-%m-%d %H:%M UTC')}</b>"
            )
    return "\n".join(lines)


async def _authorize_request_user_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user.role != UserRole.USER:
        await message.answer(t(user.ui_language, "request_user_only"))
        return None
    if user.company_id is None:
        await message.answer(t(user.ui_language, "start_choose_company"))
        return None
    return user


async def _authorize_request_user_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return None

    user = await _register_and_get_user(callback.from_user, session)
    if user.role != UserRole.USER:
        await callback.answer(t(user.ui_language, "request_user_only"), show_alert=True)
        return None
    if user.company_id is None:
        await callback.answer(t(user.ui_language, "start_choose_company"), show_alert=True)
        return None
    return user


async def _register_and_get_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User:
    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(telegram_user)
    )
    return registration.user


def _build_user_menu(user: User):
    return build_main_menu(
        role=user.role,
        has_company=user.company_id is not None,
        language=user.ui_language,
    )


async def _safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
