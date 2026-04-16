from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.request import _format_user_request_detail
from bot.handlers.request_admin import _show_request_detail_message
from bot.handlers.worker import _show_worker_request_detail
from bot.keyboards.company_chat_keyboard import (
    CompanyChatMenuCallback,
    build_company_chat_admin_root_keyboard,
    build_company_chat_company_list_keyboard,
    build_company_chat_notification_keyboard,
    build_company_chat_super_admin_root_keyboard,
    build_company_chat_user_root_keyboard,
    build_company_chat_view_keyboard,
)
from bot.keyboards.request_chat_keyboard import (
    RequestChatMenuCallback,
    RequestChatOpenCallback,
    build_request_chat_list_keyboard,
    build_request_chat_notification_keyboard,
    build_request_chat_view_keyboard,
)
from bot.keyboards.user_keyboard import build_user_request_back_keyboard
from bot.states import CompanyChatStates, RequestChatStates
from db.models import Company, CompanyChatChannel, CompanyChatMessage, Request, RequestMessage, User, UserRole
from services.chat_service import ChatAccessDeniedError, ChatService, ChatValidationError
from services.i18n import button_variants, t
from services.request_service import (
    RequestAccessDeniedError,
    RequestNotFoundError,
    RequestService,
    RequestValidationError,
)
from services.user_service import TelegramUserDTO, UserService


router = Router(name=__name__)


@router.message(Command("chats"))
@router.message(F.text.in_(button_variants("menu_request_chat")))
async def request_chat_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_message(message, session)
    if actor is None:
        return

    await state.clear()
    if actor.role in {UserRole.USER, UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        text, keyboard = await _build_company_chat_root_view(session, actor)
    else:
        text, keyboard = await _build_chat_requests_view(session, actor)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(CompanyChatMenuCallback.filter(F.action == "root"))
async def company_chat_root(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_callback(callback, session)
    if actor is None:
        return

    await state.clear()
    text, keyboard = await _build_company_chat_root_view(session, actor)
    if callback.message is not None:
        await _show_list_view(callback.message, text, keyboard)
    await callback.answer()


@router.callback_query(CompanyChatMenuCallback.filter(F.action == "companies"))
async def company_chat_choose_company(
    callback: CallbackQuery,
    callback_data: CompanyChatMenuCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_callback(callback, session)
    if actor is None:
        return

    channel = _parse_company_chat_channel(callback_data.channel)
    if channel is None:
        await callback.answer(t(actor.ui_language, "company_chat_invalid"), show_alert=True)
        return

    await state.clear()
    text, keyboard = await _build_company_chat_company_selection_view(session, actor, channel)
    if callback.message is not None:
        await _show_list_view(callback.message, text, keyboard)
    await callback.answer()


@router.callback_query(CompanyChatMenuCallback.filter(F.action == "open"))
async def company_chat_open(
    callback: CallbackQuery,
    callback_data: CompanyChatMenuCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_callback(callback, session)
    if actor is None:
        return

    channel = _parse_company_chat_channel(callback_data.channel)
    if channel is None:
        await callback.answer(t(actor.ui_language, "company_chat_invalid"), show_alert=True)
        return

    chat_service = ChatService(session)
    try:
        company, messages = await chat_service.list_company_chat_messages(
            actor,
            callback_data.company_id,
            channel,
        )
    except (ChatAccessDeniedError, ChatValidationError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.set_state(CompanyChatStates.waiting_for_message)
    await state.update_data(
        company_chat_company_id=company.id,
        company_chat_channel=channel.value,
    )

    if callback.message is not None:
        await _show_company_chat_view(
            callback.message,
            company=company,
            actor=actor,
            channel=channel,
            messages=messages,
        )
    await callback.answer()


@router.callback_query(CompanyChatMenuCallback.filter(F.action == "back"))
async def company_chat_back(
    callback: CallbackQuery,
    callback_data: CompanyChatMenuCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_callback(callback, session)
    if actor is None:
        return

    channel = _parse_company_chat_channel(callback_data.channel)
    if channel is None:
        await callback.answer(t(actor.ui_language, "company_chat_invalid"), show_alert=True)
        return

    await state.clear()
    if callback.message is not None:
        if actor.role == UserRole.SUPER_ADMIN:
            text, keyboard = await _build_company_chat_company_selection_view(session, actor, channel)
        else:
            text, keyboard = await _build_company_chat_root_view(session, actor)
        await _show_list_view(callback.message, text, keyboard)
    await callback.answer()


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
        if callback_data.source.startswith("menu_"):
            text, keyboard = await _build_chat_requests_view(session, actor)
            await _show_list_view(callback.message, text, keyboard)
        else:
            await _show_request_detail_for_source(
                callback.message,
                request=request,
                actor=actor,
                source=callback_data.source,
            )
    await callback.answer()


@router.message(CompanyChatStates.waiting_for_message, F.text)
async def company_chat_send_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_message(message, session)
    if actor is None:
        return

    data = await state.get_data()
    company_id = data.get("company_chat_company_id")
    channel_raw = data.get("company_chat_channel")
    channel = _parse_company_chat_channel(channel_raw if isinstance(channel_raw, str) else "")
    if not isinstance(company_id, int) or channel is None:
        await state.clear()
        await message.answer(t(actor.ui_language, "company_chat_invalid"))
        return

    chat_service = ChatService(session)
    try:
        chat_message = await chat_service.create_company_chat_message(
            actor,
            company_id,
            channel,
            message.text or "",
        )
        company, messages = await chat_service.list_company_chat_messages(
            actor,
            company_id,
            channel,
        )
    except (ChatAccessDeniedError, ChatValidationError) as exc:
        await message.answer(str(exc))
        return

    await message.answer(
        _format_company_chat_view_text(company, messages, actor, channel),
        reply_markup=build_company_chat_view_keyboard(actor.ui_language, company.id, channel),
    )
    await _notify_company_chat_recipients(message.bot, session, chat_message)


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


@router.message(CompanyChatStates.waiting_for_message)
async def company_chat_invalid_message(
    message: Message,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_message(message, session)
    if actor is None:
        return

    await message.answer(t(actor.ui_language, "company_chat_invalid"))


@router.message(RequestChatStates.waiting_for_message)
async def request_chat_invalid_message(
    message: Message,
    session: AsyncSession,
) -> None:
    actor = await _authorize_chat_message(message, session)
    if actor is None:
        return

    await message.answer(t(actor.ui_language, "request_chat_invalid"))


async def _notify_company_chat_recipients(
    bot: Bot,
    session: AsyncSession,
    chat_message: CompanyChatMessage,
) -> None:
    if chat_message.sender is None:
        return

    chat_service = ChatService(session)
    company, recipients = await chat_service.get_general_chat_recipients(
        chat_message.company_id,
        chat_message.channel_type,
        chat_message.sender,
    )
    sender_name = chat_message.sender.display_name

    for recipient in recipients:
        try:
            await bot.send_message(
                chat_id=recipient.telegram_id,
                text=(
                    f"{t(recipient.ui_language, 'company_chat_notification_title')}\n"
                    f"{t(recipient.ui_language, 'company_chat_company_label')}: "
                    f"<b>{escape(company.name)}</b>\n"
                    f"{t(recipient.ui_language, 'company_chat_notification_from')}: "
                    f"<b>{escape(_format_sender_label(chat_message.sender_role, sender_name, recipient))}</b>\n"
                    f"{t(recipient.ui_language, 'company_chat_message_label')}: "
                    f"<b>{escape(chat_message.text)}</b>"
                ),
                reply_markup=build_company_chat_notification_keyboard(
                    recipient.ui_language,
                    company.id,
                    chat_message.channel_type,
                ),
            )
        except Exception:
            continue


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


async def _show_company_chat_view(
    message: Message,
    *,
    company: Company,
    actor: User,
    channel: CompanyChatChannel,
    messages: list[CompanyChatMessage],
) -> None:
    text = _format_company_chat_view_text(company, messages, actor, channel)
    keyboard = build_company_chat_view_keyboard(actor.ui_language, company.id, channel)
    if message.photo:
        await _safe_clear_reply_markup(message)
        await message.answer(text, reply_markup=keyboard)
        return

    await _safe_edit_text(message, text, reply_markup=keyboard)


async def _build_company_chat_root_view(
    session: AsyncSession,
    actor: User,
) -> tuple[str, object | None]:
    chat_service = ChatService(session)

    if actor.role == UserRole.USER:
        lines = [
            t(actor.ui_language, "company_chat_root_title_user"),
            "",
        ]
        companies = await chat_service.list_companies_for_actor(actor)
        company = companies[0] if companies else None
        if company is None:
            lines.append(t(actor.ui_language, "company_chat_no_company"))
            return "\n".join(lines), None

        lines.append(t(actor.ui_language, "company_chat_root_prompt_user"))
        lines.append("")
        lines.append(f"{t(actor.ui_language, 'company_chat_company_label')}: <b>{escape(company.name)}</b>")
        return "\n".join(lines), build_company_chat_user_root_keyboard(actor.ui_language, company.id)

    if actor.role == UserRole.ADMIN:
        lines = [
            t(actor.ui_language, "company_chat_root_title_admin"),
            "",
        ]
        companies = await chat_service.list_companies_for_actor(actor)
        company = companies[0] if companies else None
        if company is None:
            lines.append(t(actor.ui_language, "company_chat_no_company"))
            return "\n".join(lines), None

        lines.append(t(actor.ui_language, "company_chat_root_prompt_admin"))
        lines.append("")
        lines.append(f"{t(actor.ui_language, 'company_chat_company_label')}: <b>{escape(company.name)}</b>")
        return "\n".join(lines), build_company_chat_admin_root_keyboard(actor.ui_language, company.id)

    if actor.role == UserRole.SUPER_ADMIN:
        lines = [
            t(actor.ui_language, "company_chat_root_title_super_admin"),
            "",
            t(actor.ui_language, "company_chat_root_prompt_super_admin"),
        ]
        return "\n".join(lines), build_company_chat_super_admin_root_keyboard(actor.ui_language)

    return await _build_chat_requests_view(session, actor)


async def _build_company_chat_company_selection_view(
    session: AsyncSession,
    actor: User,
    channel: CompanyChatChannel,
) -> tuple[str, object | None]:
    chat_service = ChatService(session)
    companies = await chat_service.list_companies_for_actor(actor)
    lines = [
        t(actor.ui_language, "company_chat_root_title_super_admin"),
        "",
        t(actor.ui_language, "company_chat_choose_company"),
        "",
    ]

    if not companies:
        lines.append(t(actor.ui_language, "company_chat_no_companies"))
        return "\n".join(lines), None

    for company in companies[:30]:
        lines.append(f"#{company.id} | {escape(company.name)}")

    return "\n".join(lines), build_company_chat_company_list_keyboard(companies[:30], actor.ui_language, channel)


async def _build_chat_requests_view(
    session: AsyncSession,
    actor: User,
) -> tuple[str, object | None]:
    request_service = RequestService(session)
    requests = await request_service.list_requests_for_chat(actor)
    source = _resolve_menu_source(actor)

    lines = [t(actor.ui_language, "request_chat_menu_title"), ""]
    if not requests:
        lines.append(t(actor.ui_language, "request_chat_menu_empty"))
        return "\n".join(lines), None

    lines.append(t(actor.ui_language, "request_chat_menu_choose"))
    lines.append("")
    for request in requests[:20]:
        title = request.user.display_name if request.user is not None else f"#{request.id}"
        lines.append(
            f"#{request.id} | {RequestService.format_status(request.status, actor.ui_language)} | {escape(title)}"
        )

    return "\n".join(lines), build_request_chat_list_keyboard(requests[:20], actor.ui_language, source)


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


def _format_company_chat_view_text(
    company: Company,
    messages: list[CompanyChatMessage],
    actor: User,
    channel: CompanyChatChannel,
) -> str:
    title_key = (
        "company_chat_title_company_users"
        if channel == CompanyChatChannel.COMPANY_USERS
        else "company_chat_title_company_admins"
    )
    lines = [
        t(actor.ui_language, title_key, company=company.name),
        "",
    ]

    if not messages:
        lines.append(t(actor.ui_language, "company_chat_empty"))
    else:
        for item in messages:
            sender_name = item.sender.display_name if item.sender is not None else "-"
            timestamp = item.created_at.strftime("%d.%m %H:%M")
            lines.append(
                f"<b>{timestamp} | {escape(_format_sender_label(item.sender_role, sender_name, actor))}</b>"
            )
            lines.append(escape(item.text))
            lines.append("")

    lines.append(t(actor.ui_language, "company_chat_prompt"))
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


def _resolve_menu_source(actor: User) -> str:
    if actor.role == UserRole.USER:
        return "menu_user"
    if actor.role == UserRole.WORKER:
        return "menu_worker"
    return "menu_manager"


def _parse_company_chat_channel(value: str) -> CompanyChatChannel | None:
    try:
        return CompanyChatChannel(value)
    except ValueError:
        return None


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


async def _show_list_view(message: Message, text: str, reply_markup=None) -> None:
    if message.photo:
        await _safe_clear_reply_markup(message)
        await message.answer(text, reply_markup=reply_markup)
        return
    await _safe_edit_text(message, text, reply_markup=reply_markup)


async def _safe_clear_reply_markup(message: Message) -> None:
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
