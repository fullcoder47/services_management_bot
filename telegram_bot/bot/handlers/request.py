from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import build_main_menu
from bot.keyboards.request_keyboard import (
    REQUEST_CREATE_CANCEL_TEXT,
    RequestMenuCallback,
    build_request_create_cancel_keyboard,
    build_request_optional_image_keyboard,
    build_request_phone_keyboard,
)
from bot.keyboards.user_keyboard import (
    UserRequestMenuCallback,
    UserRequestSelectCallback,
    build_user_request_back_keyboard,
    build_user_request_list_keyboard,
)
from bot.states import RequestCreateStates
from db.models import Request, RequestStatus, User, UserRole
from services.request_service import (
    CreateRequestDTO,
    RequestAccessDeniedError,
    RequestNotFoundError,
    RequestService,
    RequestValidationError,
)
from services.user_service import TelegramUserDTO, UserService


router = Router(name=__name__)


@router.message(Command("request"))
@router.message(F.text == "📨 Ariza qoldirish")
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
        "Telefon raqamingizni yuboring yoki pastdagi tugma orqali ulashing.",
        reply_markup=build_request_phone_keyboard(),
    )


@router.message(Command("my_requests"))
@router.message(F.text == "📄 Mening arizalarim")
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


@router.callback_query(RequestMenuCallback.filter(F.action == "cancel_create"))
async def request_create_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_callback(callback, session)
    if current_user is None:
        return

    await state.clear()
    if callback.message is not None:
        await _safe_edit_text(callback.message, "Ariza yaratish bekor qilindi.")
        await callback.message.answer(
            "Asosiy menyu",
            reply_markup=build_main_menu(current_user),
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
            "✅ Arizangiz yuborildi.\n"
            f"Ariza ID: <b>#{request.id}</b>\n"
            "Tez orada ko'rib chiqiladi.",
        )
        await callback.message.answer(
            "Asosiy menyu",
            reply_markup=build_main_menu(current_user),
        )
    await callback.answer("Ariza rasmsiz yuborildi.")
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
            _format_user_request_detail(request),
            reply_markup=build_user_request_back_keyboard(),
        )
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

    if (message.text or "").strip() == REQUEST_CREATE_CANCEL_TEXT:
        await state.clear()
        await message.answer(
            "Ariza yaratish bekor qilindi.",
            reply_markup=build_main_menu(current_user),
        )
        return

    phone = _extract_phone(message)
    if not phone:
        await message.answer(
            "Telefon raqami majburiy. Uni yozib yuboring yoki pastdagi tugma bilan ulashing.",
            reply_markup=build_request_phone_keyboard(),
        )
        return

    await state.update_data(phone=phone)
    await state.set_state(RequestCreateStates.waiting_for_problem)
    await message.answer(
        "Telefon raqamingiz qabul qilindi.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Muammo tavsifini yozing.",
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

    await state.update_data(problem_text=problem_text)
    await state.set_state(RequestCreateStates.waiting_for_image)
    await message.answer(
        "Agar xohlasangiz, muammo rasmini yuboring.\nPastdagi tugma orqali bu bosqichni o'tkazib yuborishingiz mumkin.",
        reply_markup=build_request_optional_image_keyboard(),
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

    photo = message.photo[-1]
    try:
        request = await _create_request_from_state(
            state=state,
            session=session,
            current_user=current_user,
            problem_image=photo.file_id,
        )
    except RequestValidationError as exc:
        await message.answer(str(exc), reply_markup=build_request_optional_image_keyboard())
        return

    await state.clear()
    await message.answer(
        "✅ Arizangiz yuborildi.\n"
        f"Ariza ID: <b>#{request.id}</b>\n"
        "Rasm ham biriktirildi va ariza ko'rib chiqishga yuborildi.",
        reply_markup=build_main_menu(current_user),
    )
    await _notify_management_users(message.bot, session, request)


@router.message(RequestCreateStates.waiting_for_image)
async def capture_request_image_invalid(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_user = await _authorize_request_user_message(message, session)
    if current_user is None:
        return

    await message.answer(
        "Rasm yuboring yoki pastdagi `O‘tkazib yuborish` tugmasini bosing.",
        reply_markup=build_request_optional_image_keyboard(),
    )


async def _create_request_from_state(
    state: FSMContext,
    session: AsyncSession,
    current_user: User,
    problem_image: str | None,
) -> Request:
    if current_user.company_id is None:
        raise RequestValidationError("Avval /start orqali kompaniyangizni tanlang.")

    data = await state.get_data()
    phone = str(data.get("phone", "")).strip()
    problem_text = str(data.get("problem_text", "")).strip()

    request_service = RequestService(session)
    return await request_service.create_request(
        CreateRequestDTO(
            user_id=current_user.id,
            company_id=current_user.company_id,
            phone=phone,
            problem_text=problem_text,
            problem_image=problem_image,
        )
    )


async def _build_user_requests_view(
    session: AsyncSession,
    user: User,
) -> tuple[str, object | None]:
    request_service = RequestService(session)
    requests = await request_service.list_user_requests(user.id)

    lines = ["📄 Mening arizalarim", ""]
    if not requests:
        lines.append("Sizda hozircha arizalar yo'q.")
        return "\n".join(lines), None

    lines.append("Arizalaringiz:")
    lines.append("")
    for request in requests:
        lines.append(f"#{request.id} | {RequestService.format_status(request.status)}")

    return "\n".join(lines), build_user_request_list_keyboard(requests)


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
            if request.problem_image:
                await bot.send_photo(
                    chat_id=recipient.telegram_id,
                    photo=request.problem_image,
                    caption=f"📷 Ariza #{request.id} uchun biriktirilgan rasm",
                )
        except Exception:
            continue


def _format_admin_new_request_text(request: Request) -> str:
    user_name = request.user.display_name if request.user is not None else "Noma'lum"
    company_name = request.company.name if request.company is not None else "Noma'lum kompaniya"
    lines = [
        "🆕 Yangi ariza:",
        f"🏢 Kompaniya: <b>{escape(company_name)}</b>",
        f"👤 User: <b>{escape(user_name)}</b>",
        f"📞 Telefon: <b>{escape(request.phone)}</b>",
        f"📝 Muammo: <b>{escape(request.problem_text)}</b>",
    ]
    if request.problem_image:
        lines.append("📷 Rasm: <b>biriktirilgan</b>")
    return "\n".join(lines)


def _format_user_request_detail(request: Request) -> str:
    lines = [
        f"<b>Ariza #{request.id}</b>",
        f"Holati: <b>{RequestService.format_status(request.status)}</b>",
        f"📞 Telefon: <b>{escape(request.phone)}</b>",
        f"📝 Muammo: <b>{escape(request.problem_text)}</b>",
    ]
    if request.problem_image:
        lines.append("📷 Muammo rasmi: <b>biriktirilgan</b>")
    if request.status == RequestStatus.DONE:
        lines.append(f"✅ Yakuniy izoh: <b>{escape(request.result_text or '')}</b>")
        if request.completed_at is not None:
            lines.append(f"🕒 Yakunlangan: <b>{request.completed_at.strftime('%Y-%m-%d %H:%M UTC')}</b>")
    return "\n".join(lines)


def _extract_phone(message: Message) -> str:
    if message.contact is not None and message.contact.phone_number:
        return message.contact.phone_number.strip()
    if message.text is not None:
        return message.text.strip()
    return ""


async def _authorize_request_user_message(
    message: Message,
    session: AsyncSession,
) -> User | None:
    if message.from_user is None:
        await message.answer("Telegram profilingizni aniqlab bo'lmadi.")
        return None

    user = await _register_and_get_user(message.from_user, session)
    if user.role != UserRole.USER:
        await message.answer("Bu bo'lim oddiy foydalanuvchilar uchun.")
        return None
    if user.company_id is None:
        await message.answer("Avval /start orqali kompaniyangizni tanlang.")
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
        await callback.answer("Bu bo'lim oddiy foydalanuvchilar uchun.", show_alert=True)
        return None
    if user.company_id is None:
        await callback.answer("Avval /start orqali kompaniyangizni tanlang.", show_alert=True)
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


async def _safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise
