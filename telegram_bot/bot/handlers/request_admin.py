from __future__ import annotations

from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.request_keyboard import (
    RequestActionCallback,
    RequestDoneConfirmCallback,
    RequestMenuCallback,
    RequestSelectCallback,
    build_request_admin_actions_keyboard,
    build_request_done_cancel_keyboard,
    build_request_done_confirm_keyboard,
    build_request_list_keyboard,
)
from bot.states import RequestDoneStates
from db.models import Request, RequestStatus, User, UserRole
from services.i18n import button_variants, t
from services.request_service import (
    CompleteRequestDTO,
    RequestAccessDeniedError,
    RequestNotFoundError,
    RequestService,
    RequestStateError,
    RequestValidationError,
)
from services.translation_service import TranslationService
from services.user_service import TelegramUserDTO, UserService


router = Router(name=__name__)


@router.message(Command("requests"))
@router.message(F.text.in_(button_variants("menu_requests")))
async def requests_panel_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_message(message, session)
    if current_user is None:
        return

    await state.clear()
    text, keyboard = await _build_request_list_view(session, current_user)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(RequestMenuCallback.filter(F.action == "list"))
async def requests_panel_list(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_callback(callback, session)
    if current_user is None:
        return

    await state.clear()
    text, keyboard = await _build_request_list_view(session, current_user)
    if callback.message is not None:
        await _show_request_message(callback.message, text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(RequestMenuCallback.filter(F.action == "export_excel"))
async def requests_export_excel(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_callback(callback, session)
    if current_user is None:
        return

    request_service = RequestService(session)
    try:
        excel_bytes = await request_service.export_requests_to_excel(current_user)
    except RequestAccessDeniedError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    document = BufferedInputFile(excel_bytes, filename=_build_export_filename(current_user))
    if callback.message is not None:
        await callback.message.answer_document(
            document,
            caption=t(current_user.ui_language, "requests_export_done"),
        )

    await callback.answer(t(current_user.ui_language, "excel_sent_alert"))


@router.callback_query(RequestSelectCallback.filter())
async def request_details_callback(
    callback: CallbackQuery,
    callback_data: RequestSelectCallback,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_callback(callback, session)
    if current_user is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_or_raise(callback_data.request_id)
        request_service.ensure_management_access(current_user, request)
    except (RequestNotFoundError, RequestAccessDeniedError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await callback.answer()
    if callback.message is not None:
        await _show_request_message(
            callback.message,
            await _format_request_detail(request, current_user.ui_language),
            reply_markup=build_request_admin_actions_keyboard(request, current_user.ui_language),
        )


@router.callback_query(RequestActionCallback.filter(F.action == "accept"))
async def request_accept_callback(
    callback: CallbackQuery,
    callback_data: RequestActionCallback,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_callback(callback, session)
    if current_user is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.set_in_progress(callback_data.request_id, current_user)
    except (RequestNotFoundError, RequestAccessDeniedError, RequestStateError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await callback.answer(t(current_user.ui_language, "request_accept_alert"))
    if callback.message is not None:
        await _show_request_message(
            callback.message,
            await _format_request_detail(request, current_user.ui_language),
            reply_markup=build_request_admin_actions_keyboard(request, current_user.ui_language),
        )

    await _notify_user_status_update(
        callback.bot,
        request,
        request.user.ui_language if request.user is not None else current_user.ui_language,
    )


@router.callback_query(RequestActionCallback.filter(F.action == "done"))
async def request_done_start(
    callback: CallbackQuery,
    callback_data: RequestActionCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_callback(callback, session)
    if current_user is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_or_raise(callback_data.request_id)
        request_service.ensure_management_access(current_user, request)
    except (RequestNotFoundError, RequestAccessDeniedError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if request.status == RequestStatus.DONE:
        await callback.answer(t(current_user.ui_language, "request_done_already"), show_alert=True)
        return

    await state.clear()
    await state.set_state(RequestDoneStates.waiting_for_result_text)
    await state.update_data(request_id=request.id)

    if callback.message is not None:
        await _show_request_message(
            callback.message,
            t(current_user.ui_language, "request_done_text_prompt"),
            reply_markup=build_request_done_cancel_keyboard(request.id, current_user.ui_language),
        )
    await callback.answer()


@router.message(RequestDoneStates.waiting_for_result_text)
async def request_done_capture_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_message(message, session)
    if current_user is None:
        return

    result_text = (message.text or "").strip()
    request_id = await _extract_request_id(state)
    if request_id is None:
        await state.clear()
        await message.answer(t(current_user.ui_language, "request_data_missing"))
        return

    if not result_text:
        await message.answer(
            t(current_user.ui_language, "request_result_required"),
            reply_markup=build_request_done_cancel_keyboard(request_id, current_user.ui_language),
        )
        return

    await state.update_data(result_text=result_text)
    await state.set_state(RequestDoneStates.waiting_for_result_image)
    await message.answer(
        t(current_user.ui_language, "request_done_image_prompt"),
        reply_markup=build_request_done_cancel_keyboard(request_id, current_user.ui_language),
    )


@router.message(RequestDoneStates.waiting_for_result_image, F.photo)
async def request_done_capture_image(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_message(message, session)
    if current_user is None:
        return

    request_id = await _extract_request_id(state)
    if request_id is None:
        await state.clear()
        await message.answer(t(current_user.ui_language, "request_data_missing"))
        return

    photo = message.photo[-1]
    await state.update_data(result_image=photo.file_id)
    await state.set_state(RequestDoneStates.waiting_for_confirmation)

    data = await state.get_data()
    caption = (
        f"{t(current_user.ui_language, 'request_done_summary')}\n\n"
        f"{t(current_user.ui_language, 'request_done_note_label')}: "
        f"<b>{escape(str(data.get('result_text', '')))}</b>\n"
        f"{t(current_user.ui_language, 'request_done_image_ready')}"
    )
    await message.answer_photo(
        photo.file_id,
        caption=caption,
        reply_markup=build_request_done_confirm_keyboard(request_id, current_user.ui_language),
    )


@router.message(RequestDoneStates.waiting_for_result_image)
async def request_done_require_image(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_message(message, session)
    if current_user is None:
        return

    request_id = await _extract_request_id(state)
    if request_id is None:
        await state.clear()
        await message.answer(t(current_user.ui_language, "request_data_missing"))
        return

    await message.answer(
        t(current_user.ui_language, "request_done_image_required"),
        reply_markup=build_request_done_cancel_keyboard(request_id, current_user.ui_language),
    )


@router.callback_query(
    RequestDoneConfirmCallback.filter(F.action == "cancel"),
    RequestDoneStates.waiting_for_result_text,
)
@router.callback_query(
    RequestDoneConfirmCallback.filter(F.action == "cancel"),
    RequestDoneStates.waiting_for_result_image,
)
@router.callback_query(
    RequestDoneConfirmCallback.filter(F.action == "cancel"),
    RequestDoneStates.waiting_for_confirmation,
)
async def request_done_cancel(
    callback: CallbackQuery,
    callback_data: RequestDoneConfirmCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_callback(callback, session)
    if current_user is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_or_raise(callback_data.request_id)
        request_service.ensure_management_access(current_user, request)
    except (RequestNotFoundError, RequestAccessDeniedError) as exc:
        await state.clear()
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    if callback.message is not None:
        await _safe_clear_reply_markup(callback.message)
        await callback.message.answer(
            await _format_request_detail(request, current_user.ui_language),
            reply_markup=build_request_admin_actions_keyboard(request, current_user.ui_language),
        )
    await callback.answer(t(current_user.ui_language, "request_done_cancelled"))


@router.callback_query(
    RequestDoneConfirmCallback.filter(F.action == "confirm"),
    RequestDoneStates.waiting_for_confirmation,
)
async def request_done_confirm(
    callback: CallbackQuery,
    callback_data: RequestDoneConfirmCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_manager_callback(callback, session)
    if current_user is None:
        return

    data = await state.get_data()
    request_id = data.get("request_id")
    result_text = data.get("result_text")
    result_image = data.get("result_image")

    if not isinstance(request_id, int) or not isinstance(result_text, str) or not isinstance(result_image, str):
        await state.clear()
        await callback.answer(t(current_user.ui_language, "request_data_missing"), show_alert=True)
        return

    if request_id != callback_data.request_id:
        await state.clear()
        await callback.answer(t(current_user.ui_language, "request_role_mismatch"), show_alert=True)
        return

    request_service = RequestService(session)
    try:
        request = await request_service.complete_request(
            request_id=request_id,
            actor=current_user,
            payload=CompleteRequestDTO(
                result_text=result_text,
                result_image=result_image,
            ),
        )
    except (
        RequestNotFoundError,
        RequestAccessDeniedError,
        RequestValidationError,
        RequestStateError,
    ) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    await _notify_user_request_done(callback.bot, request)

    if callback.message is not None:
        await _safe_clear_reply_markup(callback.message)
        await callback.message.answer(
            await _format_request_detail(request, current_user.ui_language),
            reply_markup=build_request_admin_actions_keyboard(request, current_user.ui_language),
        )
    await callback.answer(t(current_user.ui_language, "request_done_alert"))


async def _build_request_list_view(
    session: AsyncSession,
    actor: User,
) -> tuple[str, object | None]:
    request_service = RequestService(session)
    requests = await request_service.list_requests_for_manager(actor)
    include_export = actor.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}
    language = actor.ui_language

    lines = [t(language, "requests_title"), ""]
    lines.append(t(language, "requests_total", count=len(requests)))

    if not requests:
        lines.append("")
        lines.append(t(language, "requests_empty"))
        keyboard = (
            build_request_list_keyboard([], language=language, include_export=include_export)
            if include_export
            else None
        )
        return "\n".join(lines), keyboard

    lines.append("")
    lines.append(t(language, "requests_choose"))
    lines.append("")
    for request in requests[:20]:
        company_name = request.company.name if request.company is not None else "-"
        user_name = request.user.display_name if request.user is not None else "-"
        lines.append(
            f"#{request.id} | {RequestService.format_status(request.status, language)} | "
            f"{escape(user_name)} | {escape(company_name)}"
        )

    return "\n".join(lines), build_request_list_keyboard(
        requests,
        language=language,
        include_export=include_export,
    )


async def _format_request_detail(request: Request, language) -> str:
    user_name = request.user.display_name if request.user is not None else "Unknown"
    company_name = request.company.name if request.company is not None else "Unknown company"
    translator = TranslationService()
    translated_problem = await translator.translate_text(request.problem_text, language)
    translated_address = await translator.translate_text(request.address, language)

    lines = [
        f"<b>{t(language, 'request_detail_title', request_id=request.id)}</b>",
        f"{t(language, 'request_detail_status')}: <b>{RequestService.format_status(request.status, language)}</b>",
        f"{t(language, 'request_new_company')}: <b>{escape(company_name)}</b>",
        f"{t(language, 'request_new_user')}: <b>{escape(user_name)}</b>",
        f"{t(language, 'request_new_phone')}: <b>{escape(request.phone)}</b>",
        f"{t(language, 'request_new_problem')}: <b>{escape(translated_problem)}</b>",
        f"{t(language, 'request_new_address')}: <b>{escape(translated_address)}</b>",
    ]
    if request.problem_image:
        lines.append(t(language, "request_detail_image"))
    if request.status == RequestStatus.DONE:
        lines.append(f"{t(language, 'request_detail_done_note')}: <b>{escape(request.result_text or '')}</b>")
        if request.completed_at is not None:
            lines.append(
                f"{t(language, 'request_detail_done_at')}: <b>{request.completed_at.strftime('%Y-%m-%d %H:%M UTC')}</b>"
            )
    return "\n".join(lines)


async def _notify_user_status_update(bot: Bot, request: Request, language) -> None:
    if request.user is None:
        return

    text = "\n".join(
        [
            t(language, "request_user_accepted"),
            t(language, "request_user_progress"),
        ]
    )
    try:
        await bot.send_message(request.user.telegram_id, text)
    except Exception:
        return


async def _notify_user_request_done(bot: Bot, request: Request) -> None:
    if request.user is None:
        return

    language = request.user.ui_language
    caption = (
        f"{t(language, 'request_user_done_caption')}\n\n"
        f"{t(language, 'request_done_note_label')}: <b>{escape(request.result_text or '')}</b>\n"
        f"{t(language, 'request_done_photo_attached')}"
    )
    try:
        await bot.send_photo(
            chat_id=request.user.telegram_id,
            photo=request.result_image,
            caption=caption,
        )
    except Exception:
        try:
            await bot.send_message(
                chat_id=request.user.telegram_id,
                text=caption,
            )
        except Exception:
            return


async def _authorize_manager_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    request_service = RequestService(session)
    try:
        request_service.ensure_can_manage_requests(user)
    except RequestAccessDeniedError as exc:
        await message.answer(str(exc))
        return None

    if not user.is_super_admin and user.company_id is None:
        await message.answer(t(user.ui_language, "users_unassigned_company"))
        return None
    return user


async def _authorize_manager_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return None

    user = await _register_and_get_user(callback.from_user, session)
    request_service = RequestService(session)
    try:
        request_service.ensure_can_manage_requests(user)
    except RequestAccessDeniedError as exc:
        await callback.answer(str(exc), show_alert=True)
        return None

    if not user.is_super_admin and user.company_id is None:
        await callback.answer(t(user.ui_language, "users_unassigned_company"), show_alert=True)
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


async def _extract_request_id(state: FSMContext) -> int | None:
    data = await state.get_data()
    request_id = data.get("request_id")
    return request_id if isinstance(request_id, int) else None


async def _show_request_message(message: Message, text: str, reply_markup=None) -> None:
    if message.photo:
        await _safe_clear_reply_markup(message)
        await message.answer(text, reply_markup=reply_markup)
        return

    await _safe_edit_text(message, text, reply_markup=reply_markup)


def _build_export_filename(actor: User) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if actor.is_super_admin:
        return f"requests_{timestamp}.xlsx"
    return f"company_requests_{actor.company_id}_{timestamp}.xlsx"


async def _safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise


async def _safe_clear_reply_markup(message: Message) -> None:
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
