from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.manager_keyboard import (
    ManagerMenuCallback,
    build_broadcast_cancel_keyboard,
    build_broadcast_target_keyboard,
)
from bot.states import BroadcastStates
from db.models import User, UserRole
from services.i18n import button_variants, t
from services.user_service import TelegramUserDTO, UserAccessError, UserService


router = Router(name=__name__)


@router.message(Command("users"))
@router.message(F.text.in_(button_variants("menu_users")))
async def users_panel(
    message: Message,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    text = await _build_users_text(session, actor)
    await message.answer(text)


@router.message(Command("broadcast"))
@router.message(F.text.in_(button_variants("menu_broadcast")))
async def broadcast_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    await state.clear()
    if actor.is_super_admin:
        await state.set_state(BroadcastStates.waiting_for_target)
        await message.answer(
            t(actor.ui_language, "broadcast_target_prompt"),
            reply_markup=build_broadcast_target_keyboard(actor.ui_language),
        )
        return

    await state.set_state(BroadcastStates.waiting_for_message)
    await state.update_data(target="all")
    await message.answer(
        t(actor.ui_language, "broadcast_prompt"),
        reply_markup=build_broadcast_cancel_keyboard(actor.ui_language),
    )


@router.callback_query(
    ManagerMenuCallback.filter(F.action == "choose_target"),
    BroadcastStates.waiting_for_target,
)
async def broadcast_choose_target(
    callback: CallbackQuery,
    callback_data: ManagerMenuCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    target = callback_data.target or "all"
    await state.set_state(BroadcastStates.waiting_for_message)
    await state.update_data(target=target)

    if callback.message is not None:
        await _safe_edit_text(
            callback.message,
            t(actor.ui_language, "broadcast_prompt"),
            reply_markup=build_broadcast_cancel_keyboard(actor.ui_language),
        )
    await callback.answer()


@router.callback_query(ManagerMenuCallback.filter(F.action == "cancel_broadcast"))
async def broadcast_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    await state.clear()
    if callback.message is not None:
        await _safe_edit_text(callback.message, t(actor.ui_language, "broadcast_cancelled"))
    await callback.answer()


@router.message(BroadcastStates.waiting_for_message)
async def broadcast_send(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    content_type, payload = _extract_broadcast_payload(message)
    if payload is None:
        await message.answer(
            t(actor.ui_language, "broadcast_invalid"),
            reply_markup=build_broadcast_cancel_keyboard(actor.ui_language),
        )
        return

    target = str((await state.get_data()).get("target", "all"))
    user_service = UserService(session)
    try:
        recipients = await user_service.get_broadcast_recipients(actor, target=target)
    except UserAccessError as exc:
        await state.clear()
        await message.answer(str(exc))
        return

    sent_count = 0
    failed_count = 0
    for recipient in recipients:
        try:
            if content_type == "text":
                await message.bot.send_message(
                    chat_id=recipient.telegram_id,
                    text=payload["text"],
                    entities=payload["entities"],
                    parse_mode=None,
                )
            elif content_type == "photo":
                await message.bot.send_photo(
                    chat_id=recipient.telegram_id,
                    photo=payload["file_id"],
                    caption=payload["caption"],
                    caption_entities=payload["caption_entities"],
                    parse_mode=None,
                )
            elif content_type == "video":
                await message.bot.send_video(
                    chat_id=recipient.telegram_id,
                    video=payload["file_id"],
                    caption=payload["caption"],
                    caption_entities=payload["caption_entities"],
                    parse_mode=None,
                )
            elif content_type == "voice":
                await message.bot.send_voice(
                    chat_id=recipient.telegram_id,
                    voice=payload["file_id"],
                    caption=payload["caption"],
                    caption_entities=payload["caption_entities"],
                    parse_mode=None,
                )
            elif content_type == "video_note":
                await message.bot.send_video_note(
                    chat_id=recipient.telegram_id,
                    video_note=payload["file_id"],
                )
            elif content_type == "audio":
                await message.bot.send_audio(
                    chat_id=recipient.telegram_id,
                    audio=payload["file_id"],
                    caption=payload["caption"],
                    caption_entities=payload["caption_entities"],
                    parse_mode=None,
                )
            elif content_type == "document":
                await message.bot.send_document(
                    chat_id=recipient.telegram_id,
                    document=payload["file_id"],
                    caption=payload["caption"],
                    caption_entities=payload["caption_entities"],
                    parse_mode=None,
                )
            sent_count += 1
        except Exception:
            failed_count += 1

    await state.clear()
    await message.answer(
        t(actor.ui_language, "broadcast_sent", sent=sent_count, failed=failed_count)
    )


def _extract_broadcast_payload(message: Message):
    if message.text:
        return "text", {"text": message.text, "entities": message.entities}
    if message.photo:
        return "photo", _extract_media_payload(message.photo[-1].file_id, message)
    if message.video:
        return "video", _extract_media_payload(message.video.file_id, message)
    if message.voice:
        return "voice", _extract_media_payload(message.voice.file_id, message)
    if message.video_note:
        return "video_note", {"file_id": message.video_note.file_id}
    if message.audio:
        return "audio", _extract_media_payload(message.audio.file_id, message)
    if message.document:
        return "document", _extract_media_payload(message.document.file_id, message)
    return "", None


def _extract_media_payload(file_id: str, message: Message) -> dict[str, object]:
    return {
        "file_id": file_id,
        "caption": message.caption or None,
        "caption_entities": message.caption_entities,
    }


async def _build_users_text(session: AsyncSession, actor: User) -> str:
    user_service = UserService(session)
    users = await user_service.list_users_for_actor(actor)
    language = actor.ui_language

    lines = [t(language, "users_title"), ""]
    if not users:
        lines.append(t(language, "users_empty"))
        return "\n".join(lines)

    current_company_id = object()
    for user in users:
        if actor.is_super_admin and user.company_id != current_company_id:
            current_company_id = user.company_id
            company_label = (
                user.company.name
                if user.company is not None
                else (
                    t(language, "users_companyless")
                    if current_company_id is None
                    else f"Company ID: {current_company_id}"
                )
            )
            lines.append(f"<b>{escape(company_label)}</b>")

        lines.append(
            f"- <b>{escape(user.display_name)}</b> | {user.telegram_id} | {_format_role(user.role, language)}"
        )

    return "\n".join(lines)


async def _authorize_admin_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        await message.answer(t(user.ui_language, "users_no_access"))
        return None
    if not user.is_super_admin and user.company_id is None:
        await message.answer(t(user.ui_language, "users_unassigned_company"))
        return None
    return user


async def _authorize_admin_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> User | None:
    if callback.from_user is None:
        await callback.answer("Telegram profilingizni aniqlab bo'lmadi.", show_alert=True)
        return None

    user = await _register_and_get_user(callback.from_user, session)
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        await callback.answer(t(user.ui_language, "users_no_access"), show_alert=True)
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


def _format_role(role: UserRole, language) -> str:
    if role == UserRole.SUPER_ADMIN:
        return t(language, "role_super_admin")
    if role == UserRole.ADMIN:
        return t(language, "role_admin")
    if role == UserRole.OPERATOR:
        return t(language, "role_operator")
    return t(language, "role_user")


async def _safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)
