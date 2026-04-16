from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.request import _format_user_request_detail
from bot.handlers.request_admin import _show_request_detail_message
from bot.handlers.worker import _show_worker_request_detail
from bot.keyboards.request_chat_keyboard import (
    RequestChatMenuCallback,
    RequestChatOpenCallback,
    build_request_chat_notification_keyboard,
    build_request_chat_view_keyboard,
)
from bot.keyboards.user_keyboard import build_user_request_back_keyboard
from bot.states import RequestChatStates
from db.models import Request, RequestMessage, User, UserRole
from services.i18n import t
from services.request_service import (
    RequestAccessDeniedError,
    RequestNotFoundError,
    RequestService,
    RequestValidationError,
)
from services.user_service import TelegramUserDTO, UserService


router = Router(name=__name__)


@router.callback_query(RequestChatOpenCallback.filter())
async def request_chat_open(
    callback: CallbackQuery,
    callback_data: RequestChatOpenCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_callback(callback, session)
    if actor is None:
        return

    request_service = RequestService(session)
    try:
        request, messages = await request_service.list_request_messages_for_actor(
            callback_data.request_id,
            actor,
        )
    except (RequestNotFoundError, RequestAccessDeniedError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.set_state(RequestChatStates.waiting_for_message)
    await state.update_data(request_id=request.id, source=callback_data.source)

    if callback.message is not None:
        await _show_chat_view(
            callback.message,
            request=request,
            actor=actor,
            messages=messages,
            source=callback_data.source,
        )
    await callback.answer()


@router.callback_query(RequestChatMenuCallback.filter(F.action == "back"))
async def request_chat_back(
    callback: CallbackQuery,
    callback_data: RequestChatMenuCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_callback(callback, session)
    if actor is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_for_chat(callback_data.request_id, actor)
    except (RequestNotFoundError, RequestAccessDeniedError) as exc:
        await state.clear()
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    if callback.message is not None:
        await _show_request_detail_for_source(
            callback.message,
            request=request,
            actor=actor,
            source=callback_data.source,
        )
    await callback.answer()


@router.message(RequestChatStates.waiting_for_message, F.text)
async def request_chat_send_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_message(message, session)
    if actor is None:
        return

    data = await state.get_data()
    request_id = data.get("request_id")
    source = data.get("source")
    if not isinstance(request_id, int) or not isinstance(source, str):
        await state.clear()
        await message.answer(t(actor.ui_language, "request_data_missing"))
        return

    request_service = RequestService(session)
    try:
        chat_message = await request_service.create_request_message(
            request_id=request_id,
            actor=actor,
            text=message.text or "",
        )
        request, messages = await request_service.list_request_messages_for_actor(request_id, actor)
    except (
        RequestNotFoundError,
        RequestAccessDeniedError,
        RequestValidationError,
    ) as exc:
        await message.answer(str(exc))
        return

    await message.answer(
        _format_chat_view_text(request, messages, actor),
        reply_markup=build_request_chat_view_keyboard(request.id, actor.ui_language, source),
    )
    await _notify_chat_recipients(message.bot, session, request.id, chat_message)


@router.message(RequestChatStates.waiting_for_message)
async def request_chat_invalid_message(
    message: Message,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_message(message, session)
    if actor is None:
        return

    await message.answer(t(actor.ui_language, "request_chat_invalid"))


async def _notify_chat_recipients(
    bot: Bot,
    session: AsyncSession,
    request_id: int,
    chat_message: RequestMessage,
) -> None:
    if chat_message.sender is None:
        return

    request_service = RequestService(session)
    request, recipients = await request_service.get_request_chat_recipients(request_id, chat_message.sender)
    sender_name = chat_message.sender.display_name

    for recipient in recipients:
        try:
            await bot.send_message(
                chat_id=recipient.telegram_id,
                text=(
                    f"{t(recipient.ui_language, 'request_chat_notification_title', request_id=request.id)}\n"
                    f"{t(recipient.ui_language, 'request_chat_notification_from')}: "
                    f"<b>{escape(_format_sender_label(chat_message.sender_role, sender_name, recipient))}</b>\n"
                    f"{t(recipient.ui_language, 'request_chat_message_label')}: "
                    f"<b>{escape(chat_message.text)}</b>"
                ),
                reply_markup=build_request_chat_notification_keyboard(
                    request.id,
                    recipient.ui_language,
                    _resolve_chat_source_for_recipient(request, recipient),
                ),
            )
        except Exception:
            continue


async def _show_chat_view(
    message: Message,
    *,
    request: Request,
    actor: User,
    messages: list[RequestMessage],
    source: str,
) -> None:
    text = _format_chat_view_text(request, messages, actor)
    keyboard = build_request_chat_view_keyboard(request.id, actor.ui_language, source)
    if message.photo:
        await _safe_clear_reply_markup(message)
        await message.answer(text, reply_markup=keyboard)
        return

    await _safe_edit_text(message, text, reply_markup=keyboard)


def _format_chat_view_text(
    request: Request,
    messages: list[RequestMessage],
    actor: User,
) -> str:
    lines = [
        t(actor.ui_language, "request_chat_title", request_id=request.id),
        "",
    ]

    if not messages:
        lines.append(t(actor.ui_language, "request_chat_empty"))
    else:
        for item in messages:
            sender_name = item.sender.display_name if item.sender is not None else "-"
            timestamp = item.created_at.strftime("%d.%m %H:%M")
            lines.append(
                f"<b>{timestamp} | {escape(_format_sender_label(item.sender_role, sender_name, actor))}</b>"
            )
            lines.append(escape(item.text))
            lines.append("")

    lines.append(t(actor.ui_language, "request_chat_prompt"))
    return "\n".join(line for line in lines if line is not None).strip()


async def _show_request_detail_for_source(
    message: Message,
    *,
    request: Request,
    actor: User,
    source: str,
) -> None:
    if source == "user":
        if message.photo:
            await _safe_clear_reply_markup(message)
            await message.answer(
                _format_user_request_detail(request, actor.ui_language),
                reply_markup=build_user_request_back_keyboard(actor.ui_language, request.id),
            )
            return

        await _safe_edit_text(
            message,
            _format_user_request_detail(request, actor.ui_language),
            reply_markup=build_user_request_back_keyboard(actor.ui_language, request.id),
        )
        return

    if source.startswith("worker_"):
        view = source.removeprefix("worker_")
        await _show_worker_request_detail(message, request, actor, view)
        return

    await _show_request_detail_message(message, request, actor)


def _resolve_chat_source_for_recipient(request: Request, recipient: User) -> str:
    if recipient.role == UserRole.USER:
        return "user"
    if recipient.role == UserRole.WORKER:
        if request.completed_by_worker_id == recipient.id or request.status.value == "done":
            return "worker_done"
        if request.accepted_by_worker_id == recipient.id or request.status.value == "in_progress":
            return "worker_in_progress"
        return "worker_assigned"
    return "manager"


def _format_sender_label(sender_role: UserRole, sender_name: str, recipient: User) -> str:
    role_key = {
        UserRole.SUPER_ADMIN: "role_super_admin",
        UserRole.ADMIN: "role_admin",
        UserRole.OPERATOR: "role_operator",
        UserRole.WORKER: "role_worker",
        UserRole.USER: "role_user",
    }[sender_role]
    return f"{t(recipient.ui_language, role_key)} | {sender_name}"


async def _authorize_chat_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None
    return await _register_and_get_user(message.from_user, session)


async def _authorize_chat_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return None
    return await _register_and_get_user(callback.from_user, session)


async def _register_and_get_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User:
    user_service = UserService(session)
    registration = await user_service.register_or_update(
        TelegramUserDTO.from_aiogram_user(telegram_user)
    )
    return registration.user


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
