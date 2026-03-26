from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.manager_keyboard import ManagerMenuCallback, build_broadcast_cancel_keyboard
from bot.states import BroadcastStates
from db.models import User, UserRole
from services.user_service import (
    TelegramUserDTO,
    UserAccessError,
    UserService,
)


router = Router(name=__name__)


@router.message(Command("users"))
@router.message(F.text == "👥 Userlar")
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
@router.message(F.text == "📢 Xabar yuborish")
async def broadcast_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    await state.clear()
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer(
        "Yubormoqchi bo'lgan xabaringizni yozing",
        reply_markup=build_broadcast_cancel_keyboard(),
    )


@router.callback_query(ManagerMenuCallback.filter(F.action == "cancel_broadcast"))
async def broadcast_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Xabar yuborish bekor qilindi.")
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

    broadcast_text = (message.text or "").strip()
    if not broadcast_text:
        await message.answer(
            "Xabar matni bo'sh bo'lishi mumkin emas. Qaytadan yozing.",
            reply_markup=build_broadcast_cancel_keyboard(),
        )
        return

    user_service = UserService(session)
    try:
        recipients = await user_service.get_broadcast_recipients(actor)
    except UserAccessError as exc:
        await state.clear()
        await message.answer(str(exc))
        return

    sent_count = 0
    failed_count = 0
    for recipient in recipients:
        try:
            await message.bot.send_message(
                chat_id=recipient.telegram_id,
                text=f"📢 Xabar\n\n{broadcast_text}",
            )
            sent_count += 1
        except Exception:
            failed_count += 1

    await state.clear()
    await message.answer(
        f"✅ Xabar yuborildi.\nYuborildi: <b>{sent_count}</b>\nXato: <b>{failed_count}</b>"
    )


async def _build_users_text(session: AsyncSession, actor: User) -> str:
    user_service = UserService(session)
    users = await user_service.list_users_for_actor(actor)

    lines = ["👥 Userlar", ""]
    if not users:
        lines.append("Hozircha foydalanuvchilar yo'q.")
        return "\n".join(lines)

    current_company_id = None
    for user in users:
        if actor.is_super_admin and user.company_id != current_company_id:
            current_company_id = user.company_id
            company_label = (
                user.company.name
                if user.company is not None
                else ("Kompaniyasiz" if current_company_id is None else f"Kompaniya ID: {current_company_id}")
            )
            lines.append(f"<b>{company_label}</b>")

        lines.append(
            f"- <b>{escape(user.display_name)}</b> | {user.telegram_id} | {_format_role(user.role)}"
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
        await message.answer("Bu bo'lim faqat super admin va admin uchun.")
        return None
    if not user.is_super_admin and user.company_id is None:
        await message.answer("Siz kompaniyaga biriktirilmagansiz.")
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


def _format_role(role: UserRole) -> str:
    if role == UserRole.SUPER_ADMIN:
        return "super admin"
    if role == UserRole.ADMIN:
        return "admin"
    if role == UserRole.OPERATOR:
        return "operator"
    return "user"
