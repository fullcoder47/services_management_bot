from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.worker_keyboard import (
    WorkerDoneConfirmCallback,
    WorkerMenuCallback,
    WorkerRequestActionCallback,
    WorkerRequestSelectCallback,
    build_worker_done_cancel_keyboard,
    build_worker_done_confirm_keyboard,
    build_worker_request_actions_keyboard,
    build_worker_request_list_keyboard,
)
from bot.states import WorkerDoneStates
from db.models import Request, User, UserRole
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


@router.message(F.text.in_(button_variants("menu_worker_assigned")))
async def worker_assigned_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _show_worker_section_message(message, state, session, view="assigned")


@router.message(F.text.in_(button_variants("menu_worker_in_progress")))
async def worker_in_progress_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _show_worker_section_message(message, state, session, view="in_progress")


@router.message(F.text.in_(button_variants("menu_worker_done")))
async def worker_done_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _show_worker_section_message(message, state, session, view="done")


@router.callback_query(WorkerMenuCallback.filter())
async def worker_section_callback(
    callback: CallbackQuery,
    callback_data: WorkerMenuCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_callback(callback, session)
    if actor is None:
        return

    await state.clear()
    text, keyboard = await _build_worker_section_view(session, actor, callback_data.action)
    if callback.message is not None:
        await _show_worker_message(callback.message, text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(WorkerRequestSelectCallback.filter())
async def worker_request_detail(
    callback: CallbackQuery,
    callback_data: WorkerRequestSelectCallback,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_callback(callback, session)
    if actor is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_for_worker(callback_data.request_id, actor)
    except (RequestNotFoundError, RequestAccessDeniedError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if callback.message is not None:
        await _show_worker_request_detail(callback.message, request, actor, callback_data.view)
    await callback.answer()


@router.callback_query(WorkerRequestActionCallback.filter(F.action == "accept"))
async def worker_request_accept(
    callback: CallbackQuery,
    callback_data: WorkerRequestActionCallback,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_callback(callback, session)
    if actor is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.accept_request_by_worker(callback_data.request_id, actor)
    except (RequestNotFoundError, RequestAccessDeniedError, RequestStateError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await _notify_admins_request_accepted(callback.bot, session, request, actor)
    await _notify_user_request_accepted(callback.bot, request)
    if callback.message is not None:
        await _show_worker_request_detail(callback.message, request, actor, callback_data.view)
    await callback.answer(t(actor.ui_language, "worker_accept_alert"))


@router.callback_query(WorkerRequestActionCallback.filter(F.action == "done"))
async def worker_request_done_start(
    callback: CallbackQuery,
    callback_data: WorkerRequestActionCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_callback(callback, session)
    if actor is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_for_worker(callback_data.request_id, actor)
        request_service.ensure_completion_access(actor, request)
    except (RequestNotFoundError, RequestAccessDeniedError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    await state.set_state(WorkerDoneStates.waiting_for_result_text)
    await state.update_data(request_id=request.id, view=callback_data.view)
    if callback.message is not None:
        await _show_worker_message(
            callback.message,
            t(actor.ui_language, "request_done_text_prompt"),
            reply_markup=build_worker_done_cancel_keyboard(
                request.id,
                language=actor.ui_language,
                view=callback_data.view,
            ),
        )
    await callback.answer()


@router.message(WorkerDoneStates.waiting_for_result_text)
async def worker_capture_done_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_message(message, session)
    if actor is None:
        return

    result_text = (message.text or "").strip()
    request_id = await _extract_request_id(state)
    view = await _extract_view(state)
    if request_id is None or view is None:
        await state.clear()
        await message.answer(t(actor.ui_language, "request_data_missing"))
        return

    if not result_text:
        await message.answer(
            t(actor.ui_language, "request_result_required"),
            reply_markup=build_worker_done_cancel_keyboard(request_id, language=actor.ui_language, view=view),
        )
        return

    await state.update_data(result_text=result_text)
    await state.set_state(WorkerDoneStates.waiting_for_result_image)
    await message.answer(
        t(actor.ui_language, "request_done_image_prompt"),
        reply_markup=build_worker_done_cancel_keyboard(
            request_id,
            language=actor.ui_language,
            view=view,
            allow_skip=True,
        ),
    )


@router.message(WorkerDoneStates.waiting_for_result_image, F.photo)
async def worker_capture_done_image(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_message(message, session)
    if actor is None:
        return

    request_id = await _extract_request_id(state)
    view = await _extract_view(state)
    if request_id is None or view is None:
        await state.clear()
        await message.answer(t(actor.ui_language, "request_data_missing"))
        return

    await state.update_data(result_image=message.photo[-1].file_id)
    await state.set_state(WorkerDoneStates.waiting_for_confirmation)
    data = await state.get_data()
    await message.answer_photo(
        message.photo[-1].file_id,
        caption=(
            f"{t(actor.ui_language, 'request_done_summary')}\n\n"
            f"{t(actor.ui_language, 'request_done_note_label')}: "
            f"<b>{escape(str(data.get('result_text', '')))}</b>"
        ),
        reply_markup=build_worker_done_confirm_keyboard(request_id, language=actor.ui_language, view=view),
    )


@router.callback_query(
    WorkerDoneConfirmCallback.filter(F.action == "skip"),
    WorkerDoneStates.waiting_for_result_image,
)
async def worker_skip_done_image(
    callback: CallbackQuery,
    callback_data: WorkerDoneConfirmCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_callback(callback, session)
    if actor is None:
        return

    request_id = await _extract_request_id(state)
    view = await _extract_view(state)
    if request_id is None or view is None or request_id != callback_data.request_id:
        await state.clear()
        await callback.answer(t(actor.ui_language, "request_data_missing"), show_alert=True)
        return

    await state.update_data(result_image=None)
    await state.set_state(WorkerDoneStates.waiting_for_confirmation)
    data = await state.get_data()
    summary = (
        f"{t(actor.ui_language, 'request_done_summary')}\n\n"
        f"{t(actor.ui_language, 'request_done_note_label')}: "
        f"<b>{escape(str(data.get('result_text', '')))}</b>\n"
        f"{t(actor.ui_language, 'request_done_no_image')}"
    )
    if callback.message is not None:
        await _show_worker_message(
            callback.message,
            summary,
            reply_markup=build_worker_done_confirm_keyboard(
                request_id,
                language=actor.ui_language,
                view=view,
            ),
        )
    await callback.answer()


@router.message(WorkerDoneStates.waiting_for_result_image)
async def worker_capture_done_image_invalid(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_message(message, session)
    if actor is None:
        return

    request_id = await _extract_request_id(state)
    view = await _extract_view(state)
    if request_id is None or view is None:
        await state.clear()
        await message.answer(t(actor.ui_language, "request_data_missing"))
        return

    await message.answer(
        t(actor.ui_language, "request_done_image_required"),
        reply_markup=build_worker_done_cancel_keyboard(
            request_id,
            language=actor.ui_language,
            view=view,
            allow_skip=True,
        ),
    )


@router.callback_query(
    WorkerDoneConfirmCallback.filter(F.action == "cancel"),
    WorkerDoneStates.waiting_for_result_text,
)
@router.callback_query(
    WorkerDoneConfirmCallback.filter(F.action == "cancel"),
    WorkerDoneStates.waiting_for_result_image,
)
@router.callback_query(
    WorkerDoneConfirmCallback.filter(F.action == "cancel"),
    WorkerDoneStates.waiting_for_confirmation,
)
async def worker_done_cancel(
    callback: CallbackQuery,
    callback_data: WorkerDoneConfirmCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_callback(callback, session)
    if actor is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_for_worker(callback_data.request_id, actor)
    except (RequestNotFoundError, RequestAccessDeniedError) as exc:
        await state.clear()
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    if callback.message is not None:
        await _show_worker_request_detail(callback.message, request, actor, callback_data.view)
    await callback.answer(t(actor.ui_language, "request_done_cancelled"))


@router.callback_query(
    WorkerDoneConfirmCallback.filter(F.action == "confirm"),
    WorkerDoneStates.waiting_for_confirmation,
)
async def worker_done_confirm(
    callback: CallbackQuery,
    callback_data: WorkerDoneConfirmCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_worker_callback(callback, session)
    if actor is None:
        return

    data = await state.get_data()
    request_id = data.get("request_id")
    result_text = data.get("result_text")
    result_image = data.get("result_image")
    if (
        not isinstance(request_id, int)
        or not isinstance(result_text, str)
        or (result_image is not None and not isinstance(result_image, str))
    ):
        await state.clear()
        await callback.answer(t(actor.ui_language, "request_data_missing"), show_alert=True)
        return

    request_service = RequestService(session)
    try:
        request = await request_service.complete_request(
            request_id=request_id,
            actor=actor,
            payload=CompleteRequestDTO(result_text=result_text, result_image=result_image),
        )
    except (
        RequestNotFoundError,
        RequestAccessDeniedError,
        RequestStateError,
        RequestValidationError,
    ) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    await _notify_admins_request_done(callback.bot, session, request, actor)
    await _notify_user_request_done(callback.bot, request, actor)
    if callback.message is not None:
        await _show_worker_request_detail(callback.message, request, actor, callback_data.view)
    await callback.answer(t(actor.ui_language, "worker_done_alert"))


async def _show_worker_section_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    view: str,
) -> None:
    actor = await _authorize_worker_message(message, session)
    if actor is None:
        return

    await state.clear()
    text, keyboard = await _build_worker_section_view(session, actor, view)
    await message.answer(text, reply_markup=keyboard)


async def _build_worker_section_view(
    session: AsyncSession,
    actor: User,
    view: str,
) -> tuple[str, object | None]:
    request_service = RequestService(session)
    requests = await request_service.list_requests_for_worker(actor, view=view)

    title_key = {
        "assigned": "worker_section_title_assigned",
        "in_progress": "worker_section_title_in_progress",
        "done": "worker_section_title_done",
    }[view]
    empty_key = {
        "assigned": "worker_requests_empty_assigned",
        "in_progress": "worker_requests_empty_in_progress",
        "done": "worker_requests_empty_done",
    }[view]

    lines = [t(actor.ui_language, title_key), ""]
    if not requests:
        lines.append(t(actor.ui_language, empty_key))
        return "\n".join(lines), None

    lines.append(t(actor.ui_language, "worker_requests_choose"))
    lines.append("")
    for request in requests:
        lines.append(f"#{request.id} | {RequestService.format_status(request.status, actor.ui_language)}")

    return "\n".join(lines), build_worker_request_list_keyboard(
        requests,
        language=actor.ui_language,
        view=view,
    )


async def _show_worker_request_detail(
    message: Message,
    request: Request,
    actor: User,
    view: str,
) -> None:
    translator = TranslationService()
    problem_text = await translator.translate_text(request.problem_text, actor.ui_language)
    address_text = await translator.translate_text(request.address or "", actor.ui_language)
    creator = request.creator_admin.display_name if request.creator_admin is not None else "-"
    accepted_by = request.accepted_by_worker.display_name if request.accepted_by_worker is not None else "-"
    completed_by = request.completed_by_worker.display_name if request.completed_by_worker is not None else "-"

    lines = [
        f"<b>{t(actor.ui_language, 'request_detail_title', request_id=request.id)}</b>",
        f"{t(actor.ui_language, 'request_detail_status')}: <b>{RequestService.format_status(request.status, actor.ui_language)}</b>",
        f"{t(actor.ui_language, 'admin_request_creator')}: <b>{escape(creator)}</b>",
        f"{t(actor.ui_language, 'request_new_phone')}: <b>{escape(request.phone)}</b>",
        f"{t(actor.ui_language, 'request_new_problem')}: <b>{escape(problem_text)}</b>",
        f"{t(actor.ui_language, 'request_new_address')}: <b>{escape(address_text or t(actor.ui_language, 'request_no_address'))}</b>",
        f"{t(actor.ui_language, 'request_detail_accepted_by_worker')}: <b>{escape(accepted_by)}</b>",
        f"{t(actor.ui_language, 'request_detail_completed_by_worker')}: <b>{escape(completed_by)}</b>",
    ]
    if request.problem_image:
        lines.append(t(actor.ui_language, "request_detail_image"))
    text = "\n".join(lines)
    keyboard = build_worker_request_actions_keyboard(request, language=actor.ui_language, actor=actor, view=view)

    if request.problem_image:
        if message.photo:
            try:
                await message.edit_caption(caption=text, reply_markup=keyboard)
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc):
                    return

        await _safe_clear_reply_markup(message)
        try:
            await message.answer_photo(request.problem_image, caption=text, reply_markup=keyboard)
            return
        except TelegramBadRequest:
            await message.answer(text, reply_markup=keyboard)
            return

    await _show_worker_message(message, text, reply_markup=keyboard)


async def _notify_admins_request_accepted(bot, session: AsyncSession, request: Request, worker: User) -> None:
    request_service = RequestService(session)
    recipients = await request_service.get_admin_recipients(request.company_id)
    if request.creator_admin is not None:
        recipients = [request.creator_admin, *recipients]
    sent_to: set[int] = set()
    for recipient in recipients:
        if recipient.telegram_id in sent_to:
            continue
        sent_to.add(recipient.telegram_id)
        try:
            await bot.send_message(
                recipient.telegram_id,
                t(recipient.ui_language, "worker_accept_notification_admin", worker=escape(worker.display_name)),
            )
        except Exception:
            continue


async def _notify_user_request_accepted(bot, request: Request) -> None:
    if request.source_type.value != "user" or request.user is None or request.user.role != UserRole.USER:
        return
    text = "\n".join(
        [
            t(request.user.ui_language, "request_user_accepted"),
            t(request.user.ui_language, "request_user_progress"),
        ]
    )
    try:
        await bot.send_message(request.user.telegram_id, text)
    except Exception:
        return


async def _notify_admins_request_done(bot, session: AsyncSession, request: Request, worker: User) -> None:
    request_service = RequestService(session)
    recipients = await request_service.get_admin_recipients(request.company_id)
    if request.creator_admin is not None:
        recipients = [request.creator_admin, *recipients]
    sent_to: set[int] = set()
    for recipient in recipients:
        if recipient.telegram_id in sent_to:
            continue
        sent_to.add(recipient.telegram_id)
        try:
            await bot.send_message(
                recipient.telegram_id,
                t(recipient.ui_language, "worker_done_notification_admin", worker=escape(worker.display_name)),
            )
        except Exception:
            continue


async def _notify_user_request_done(bot, request: Request, worker: User) -> None:
    if request.source_type.value != "user" or request.user is None or request.user.role != UserRole.USER:
        return

    caption = t(
        request.user.ui_language,
        "worker_done_caption_with_name",
        worker=escape(worker.display_name),
        note=escape(request.result_text or ""),
    )

    if request.result_image:
        try:
            await bot.send_photo(
                chat_id=request.user.telegram_id,
                photo=request.result_image,
                caption=caption,
            )
        except Exception:
            try:
                await bot.send_message(request.user.telegram_id, caption)
            except Exception:
                return
        return

    try:
        await bot.send_message(request.user.telegram_id, caption)
    except Exception:
        return


async def _authorize_worker_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user.role != UserRole.WORKER:
        await message.answer(t(user.ui_language, "worker_no_access"))
        return None
    if user.company_id is None:
        await message.answer(t(user.ui_language, "worker_unassigned_company"))
        return None
    return user


async def _authorize_worker_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return None

    user = await _register_and_get_user(callback.from_user, session)
    if user.role != UserRole.WORKER:
        await callback.answer(t(user.ui_language, "worker_no_access"), show_alert=True)
        return None
    if user.company_id is None:
        await callback.answer(t(user.ui_language, "worker_unassigned_company"), show_alert=True)
        return None
    return user


async def _register_and_get_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User:
    user_service = UserService(session)
    registration = await user_service.register_or_update(TelegramUserDTO.from_aiogram_user(telegram_user))
    return registration.user


async def _extract_request_id(state: FSMContext) -> int | None:
    request_id = (await state.get_data()).get("request_id")
    return request_id if isinstance(request_id, int) else None


async def _extract_view(state: FSMContext) -> str | None:
    view = (await state.get_data()).get("view")
    return view if isinstance(view, str) else None


async def _show_worker_message(message: Message, text: str, reply_markup=None) -> None:
    if message.photo:
        await _safe_clear_reply_markup(message)
        await message.answer(text, reply_markup=reply_markup)
        return
    await _safe_edit_text(message, text, reply_markup=reply_markup)


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
