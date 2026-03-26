from __future__ import annotations

from html import escape

from aiogram import F, Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.request_keyboard import (
    RequestMenuCallback,
    build_request_create_cancel_keyboard,
)
from bot.states import RequestCreateStates
from db.models import Request, User
from services.request_service import CreateRequestDTO, RequestService, RequestValidationError
from services.user_service import TelegramUserDTO, UserService


router = Router(name=__name__)


@router.message(Command("request"))
@router.message(F.text == "📝 Ariza qoldirish")
async def request_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    await state.clear()
    await state.set_state(RequestCreateStates.waiting_for_phone)
    await message.answer(
        "Telefon raqamingizni yuboring",
        reply_markup=build_request_create_cancel_keyboard(),
    )


@router.callback_query(RequestMenuCallback.filter(F.action == "cancel_create"))
async def request_create_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    if callback.message is not None:
        await _safe_edit_text(callback.message, "Ariza yaratish bekor qilindi.")
    await callback.answer()


@router.message(RequestCreateStates.waiting_for_phone)
async def capture_request_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    phone = (message.text or "").strip()
    if not phone:
        await message.answer(
            "Telefon raqami majburiy. Qaytadan yuboring.",
            reply_markup=build_request_create_cancel_keyboard(),
        )
        return

    await state.update_data(phone=phone)
    await state.set_state(RequestCreateStates.waiting_for_problem)
    await message.answer(
        "Muammoni yozing",
        reply_markup=build_request_create_cancel_keyboard(),
    )


@router.message(RequestCreateStates.waiting_for_problem)
async def capture_request_problem(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    problem_text = (message.text or "").strip()
    if not problem_text:
        await message.answer(
            "Muammo tavsifi majburiy. Qaytadan yuboring.",
            reply_markup=build_request_create_cancel_keyboard(),
        )
        return

    if current_user.company_id is None:
        await state.clear()
        await message.answer("Siz kompaniyaga biriktirilmagansiz. Ariza yubora olmaysiz.")
        return

    data = await state.get_data()
    request_service = RequestService(session)

    try:
        request = await request_service.create_request(
            CreateRequestDTO(
                user_id=current_user.id,
                company_id=current_user.company_id,
                phone=str(data.get("phone", "")).strip(),
                problem_text=problem_text,
            )
        )
    except RequestValidationError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    await message.answer(
        "✅ Arizangiz yuborildi.\n"
        f"Ariza ID: <b>#{request.id}</b>\n"
        "Tez orada ko'rib chiqiladi."
    )
    await _notify_management_users(message.bot, session, request)


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
    text = _format_admin_new_request_text(request)
    from bot.keyboards.request_keyboard import build_request_admin_actions_keyboard

    for recipient in recipients:
        try:
            await bot.send_message(
                chat_id=recipient.telegram_id,
                text=text,
                reply_markup=build_request_admin_actions_keyboard(request),
            )
        except Exception:
            continue


def _format_admin_new_request_text(request: Request) -> str:
    user_name = request.user.display_name if request.user is not None else "Noma'lum"
    return (
        "🆕 Yangi ariza:\n"
        f"👤 User: <b>{escape(user_name)}</b>\n"
        f"📞 Telefon: <b>{escape(request.phone)}</b>\n"
        f"📝 Muammo: <b>{escape(request.problem_text)}</b>"
    )


async def _authorize_request_user_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user.company_id is None:
        await message.answer("Siz kompaniyaga biriktirilmagansiz. Ariza yubora olmaysiz.")
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


async def _safe_edit_text(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
