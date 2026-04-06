from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin_request_keyboard import (
    AdminRequestCompanyCallback,
    AdminRequestConfirmCallback,
    AdminRequestMenuCallback,
    AdminRequestWorkerToggleCallback,
    build_admin_request_cancel_keyboard,
    build_admin_request_company_keyboard,
    build_admin_request_create_confirm_keyboard,
    build_admin_request_optional_image_keyboard,
    build_admin_request_workers_keyboard,
)
from bot.keyboards.request_keyboard import RequestActionCallback, build_request_admin_actions_keyboard
from bot.keyboards.worker_keyboard import build_worker_assignment_message_keyboard
from bot.states import AdminRequestStates
from db.models import Company, Request, User, UserRole
from services.company_service import CompanyService
from services.i18n import button_variants, t
from services.request_service import (
    CreateAdminRequestDTO,
    RequestAccessDeniedError,
    RequestNotFoundError,
    RequestService,
    RequestStateError,
    RequestValidationError,
)
from services.translation_service import TranslationService
from services.user_service import (
    TelegramUserDTO,
    UserService,
    UserValidationError,
)


router = Router(name=__name__)


@router.message(Command("create_request"))
@router.message(F.text.in_(button_variants("menu_create_request")))
async def admin_create_request_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    await state.clear()
    await state.update_data(flow_mode="create")
    if actor.is_super_admin:
        companies = await CompanyService(session).list_companies()
        await state.set_state(AdminRequestStates.waiting_for_company)
        await message.answer(
            t(actor.ui_language, "admin_request_choose_company"),
            reply_markup=build_admin_request_company_keyboard(companies, actor.ui_language) if companies else None,
        )
        return

    if actor.company_id is None:
        await message.answer(t(actor.ui_language, "users_unassigned_company"))
        return

    await state.update_data(company_id=actor.company_id)
    await state.set_state(AdminRequestStates.waiting_for_problem)
    await message.answer(
        t(actor.ui_language, "admin_request_problem_prompt"),
        reply_markup=build_admin_request_cancel_keyboard(actor.ui_language),
    )


@router.callback_query(RequestActionCallback.filter(F.action == "assign_workers"))
async def assign_workers_start(
    callback: CallbackQuery,
    callback_data: RequestActionCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    request_service = RequestService(session)
    try:
        request = await request_service.get_request_or_raise(callback_data.request_id)
        request_service.ensure_can_assign_workers(actor, request)
    except (RequestNotFoundError, RequestAccessDeniedError, RequestStateError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    workers = await UserService(session).list_workers_for_actor(actor, request.company_id)
    selected_ids = {worker.id for worker in request.assigned_workers}

    await state.clear()
    await state.set_state(AdminRequestStates.waiting_for_workers)
    await state.update_data(
        flow_mode="assign",
        request_id=request.id,
        company_id=request.company_id,
        selected_worker_ids=list(selected_ids),
        use_all_workers=False,
    )

    if callback.message is not None:
        text = await _build_workers_selection_text(actor, session, request.company_id, selected_ids)
        await _show_text_message(
            callback.message,
            text,
            reply_markup=build_admin_request_workers_keyboard(
                workers,
                selected_ids,
                actor.ui_language,
                allow_confirm=bool(selected_ids),
                allow_skip=False,
            ),
        )
    await callback.answer()


@router.callback_query(AdminRequestCompanyCallback.filter(), AdminRequestStates.waiting_for_company)
async def admin_request_select_company(
    callback: CallbackQuery,
    callback_data: AdminRequestCompanyCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    company = await CompanyService(session).get_company(callback_data.company_id)
    if company is None:
        await callback.answer("Kompaniya topilmadi.", show_alert=True)
        return

    await state.update_data(company_id=company.id)
    await state.set_state(AdminRequestStates.waiting_for_problem)
    if callback.message is not None:
        await _show_text_message(
            callback.message,
            t(actor.ui_language, "admin_request_problem_prompt"),
            reply_markup=build_admin_request_cancel_keyboard(actor.ui_language),
        )
    await callback.answer()


@router.message(AdminRequestStates.waiting_for_problem)
async def admin_request_capture_problem(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    problem_text = (message.text or "").strip()
    if not problem_text:
        await message.answer(
            t(actor.ui_language, "admin_request_problem_required"),
            reply_markup=build_admin_request_cancel_keyboard(actor.ui_language),
        )
        return

    await state.update_data(problem_text=problem_text)
    await state.set_state(AdminRequestStates.waiting_for_phone)
    await message.answer(
        t(actor.ui_language, "admin_request_phone_prompt"),
        reply_markup=build_admin_request_cancel_keyboard(actor.ui_language),
    )


@router.message(AdminRequestStates.waiting_for_phone)
async def admin_request_capture_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    phone = (message.text or "").strip()
    if not phone:
        await message.answer(
            t(actor.ui_language, "admin_request_phone_required"),
            reply_markup=build_admin_request_cancel_keyboard(actor.ui_language),
        )
        return

    try:
        normalized_phone = UserService.normalize_phone_number(phone)
    except UserValidationError:
        await message.answer(
            t(actor.ui_language, "admin_request_phone_invalid"),
            reply_markup=build_admin_request_cancel_keyboard(actor.ui_language),
        )
        return

    await state.update_data(phone=normalized_phone)
    await state.set_state(AdminRequestStates.waiting_for_image)
    await message.answer(
        t(actor.ui_language, "admin_request_image_prompt"),
        reply_markup=build_admin_request_optional_image_keyboard(actor.ui_language),
    )


@router.message(AdminRequestStates.waiting_for_image, F.photo)
async def admin_request_capture_image(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    await state.update_data(problem_image=message.photo[-1].file_id)
    await _show_worker_selection_message(message, state, session, actor)


@router.message(AdminRequestStates.waiting_for_image)
async def admin_request_capture_image_invalid(
    message: Message,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_message(message, session)
    if actor is None:
        return

    await message.answer(
        t(actor.ui_language, "admin_request_image_invalid"),
        reply_markup=build_admin_request_optional_image_keyboard(actor.ui_language),
    )


@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "skip_image"),
    AdminRequestStates.waiting_for_image,
)
async def admin_request_skip_image(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    await state.update_data(problem_image=None)
    if callback.message is not None:
        await _show_worker_selection_callback(callback.message, state, session, actor)
    await callback.answer()


@router.callback_query(
    AdminRequestWorkerToggleCallback.filter(),
    AdminRequestStates.waiting_for_workers,
)
async def admin_request_toggle_worker(
    callback: CallbackQuery,
    callback_data: AdminRequestWorkerToggleCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    company_id = await _extract_company_id(state)
    if company_id is None:
        await state.clear()
        await callback.answer(t(actor.ui_language, "workers_choose_company"), show_alert=True)
        return

    selected_ids = set(await _extract_selected_worker_ids(state))
    flow_mode = str((await state.get_data()).get("flow_mode", "create"))
    if callback_data.worker_id in selected_ids:
        selected_ids.remove(callback_data.worker_id)
    else:
        selected_ids.add(callback_data.worker_id)
    await state.update_data(selected_worker_ids=list(selected_ids))

    workers = await UserService(session).list_workers_for_actor(actor, company_id)
    if callback.message is not None:
        text = await _build_workers_selection_text(actor, session, company_id, selected_ids)
        await _show_text_message(
            callback.message,
            text,
            reply_markup=build_admin_request_workers_keyboard(
                workers,
                selected_ids,
                actor.ui_language,
                allow_confirm=bool(selected_ids),
                allow_skip=flow_mode == "create",
            ),
        )
    await callback.answer()


@router.callback_query(
    AdminRequestConfirmCallback.filter(F.action == "confirm_workers"),
    AdminRequestStates.waiting_for_workers,
)
async def admin_request_confirm_workers(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    company_id = await _extract_company_id(state)
    selected_ids = set(await _extract_selected_worker_ids(state))
    if company_id is None or not selected_ids:
        await callback.answer(t(actor.ui_language, "admin_request_workers_empty"), show_alert=True)
        return

    workers = await UserService(session).get_workers_for_company_ids(company_id, list(selected_ids))
    if not workers:
        await callback.answer(t(actor.ui_language, "admin_request_workers_empty"), show_alert=True)
        return

    await state.update_data(use_all_workers=False)
    await state.update_data(selected_worker_ids=[worker.id for worker in workers])
    await state.set_state(AdminRequestStates.waiting_for_confirmation)

    if callback.message is not None:
        await _show_text_message(
            callback.message,
            await _build_confirmation_text(actor, state, workers, session),
            reply_markup=build_admin_request_create_confirm_keyboard(actor.ui_language),
        )
    await callback.answer()


@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "skip_workers"),
    AdminRequestStates.waiting_for_workers,
)
async def admin_request_skip_workers(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    data = await state.get_data()
    flow_mode = str(data.get("flow_mode", "create"))
    if flow_mode != "create":
        await callback.answer(t(actor.ui_language, "request_data_missing"), show_alert=True)
        return

    company_id = await _extract_company_id(state)
    if company_id is None:
        await state.clear()
        await callback.answer(t(actor.ui_language, "workers_choose_company"), show_alert=True)
        return

    workers = await UserService(session).list_workers_for_actor(actor, company_id)
    await state.update_data(use_all_workers=True, selected_worker_ids=[])
    await state.set_state(AdminRequestStates.waiting_for_confirmation)

    if callback.message is not None:
        await _show_text_message(
            callback.message,
            await _build_confirmation_text(actor, state, workers, session),
            reply_markup=build_admin_request_create_confirm_keyboard(actor.ui_language),
        )
    await callback.answer()


@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "back"),
    AdminRequestStates.waiting_for_workers,
)
async def admin_request_workers_back(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    data = await state.get_data()
    flow_mode = str(data.get("flow_mode", "create"))
    if flow_mode == "assign":
        request_id = data.get("request_id")
        if not isinstance(request_id, int):
            await state.clear()
            await callback.answer(t(actor.ui_language, "request_data_missing"), show_alert=True)
            return

        request_service = RequestService(session)
        try:
            request = await request_service.get_request_or_raise(request_id)
            request_service.ensure_can_assign_workers(actor, request)
        except (RequestNotFoundError, RequestAccessDeniedError, RequestStateError) as exc:
            await state.clear()
            await callback.answer(str(exc), show_alert=True)
            return

        await state.clear()
        if callback.message is not None:
            await _show_request_result(callback.message, request, actor, prefix_text="")
        await callback.answer()
        return

    await state.set_state(AdminRequestStates.waiting_for_image)
    if callback.message is not None:
        await _show_text_message(
            callback.message,
            t(actor.ui_language, "admin_request_image_prompt"),
            reply_markup=build_admin_request_optional_image_keyboard(actor.ui_language),
        )
    await callback.answer()


@router.callback_query(
    AdminRequestConfirmCallback.filter(F.action == "confirm_create"),
    AdminRequestStates.waiting_for_confirmation,
)
async def admin_request_submit(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    data = await state.get_data()
    flow_mode = str(data.get("flow_mode", "create"))
    company_id = data.get("company_id")
    selected_ids = data.get("selected_worker_ids", [])
    use_all_workers = bool(data.get("use_all_workers", False))
    if not isinstance(company_id, int) or not isinstance(selected_ids, list):
        await state.clear()
        await callback.answer(t(actor.ui_language, "request_data_missing"), show_alert=True)
        return

    user_service = UserService(session)
    if flow_mode == "assign":
        workers = await user_service.get_workers_for_company_ids(company_id, [int(worker_id) for worker_id in selected_ids])
        if not workers:
            await state.clear()
            await callback.answer(t(actor.ui_language, "admin_request_workers_empty"), show_alert=True)
            return
    elif use_all_workers:
        workers = await user_service.list_workers_for_actor(actor, company_id)
    else:
        workers = await user_service.get_workers_for_company_ids(company_id, [int(worker_id) for worker_id in selected_ids])

    request_service = RequestService(session)
    try:
        if flow_mode == "assign":
            request_id = data.get("request_id")
            if not isinstance(request_id, int):
                raise RequestValidationError(t(actor.ui_language, "request_data_missing"))
            request = await request_service.assign_workers(request_id, actor, workers)
            success_text = t(actor.ui_language, "admin_request_assign_success")
        else:
            payload = CreateAdminRequestDTO(
                company_id=company_id,
                phone=str(data.get("phone", "")),
                problem_text=str(data.get("problem_text", "")),
                problem_image=data.get("problem_image") if isinstance(data.get("problem_image"), str) else None,
                worker_ids=[worker.id for worker in workers],
            )
            request = await request_service.create_admin_request(actor, payload, workers)
            success_text = t(actor.ui_language, "admin_request_created")
    except (
        RequestAccessDeniedError,
        RequestNotFoundError,
        RequestStateError,
        RequestValidationError,
    ) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    await _notify_workers_assigned(callback.bot, request)

    if callback.message is not None:
        await _show_request_result(callback.message, request, actor, prefix_text=success_text)
    await callback.answer()


@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "back_to_workers"),
    AdminRequestStates.waiting_for_confirmation,
)
async def admin_request_back_to_workers(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    await state.set_state(AdminRequestStates.waiting_for_workers)
    company_id = await _extract_company_id(state)
    if company_id is None:
        await state.clear()
        await callback.answer(t(actor.ui_language, "workers_choose_company"), show_alert=True)
        return

    selected_ids = set(await _extract_selected_worker_ids(state))
    flow_mode = str((await state.get_data()).get("flow_mode", "create"))
    workers = await UserService(session).list_workers_for_actor(actor, company_id)
    if callback.message is not None:
        text = await _build_workers_selection_text(actor, session, company_id, selected_ids)
        await _show_text_message(
            callback.message,
            text,
            reply_markup=build_admin_request_workers_keyboard(
                workers,
                selected_ids,
                actor.ui_language,
                allow_confirm=bool(selected_ids),
                allow_skip=flow_mode == "create",
            ),
        )
    await callback.answer()


@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "cancel"),
    AdminRequestStates.waiting_for_company,
)
@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "cancel"),
    AdminRequestStates.waiting_for_problem,
)
@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "cancel"),
    AdminRequestStates.waiting_for_phone,
)
@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "cancel"),
    AdminRequestStates.waiting_for_image,
)
@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "cancel"),
    AdminRequestStates.waiting_for_workers,
)
@router.callback_query(
    AdminRequestMenuCallback.filter(F.action == "cancel"),
    AdminRequestStates.waiting_for_confirmation,
)
async def admin_request_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    actor = await _authorize_admin_callback(callback, session)
    if actor is None:
        return

    await state.clear()
    if callback.message is not None:
        await _show_text_message(callback.message, t(actor.ui_language, "request_cancelled"))
    await callback.answer()


async def _show_worker_selection_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    actor: User,
) -> None:
    company_id = await _extract_company_id(state)
    if company_id is None:
        await state.clear()
        await message.answer(t(actor.ui_language, "workers_choose_company"))
        return

    await state.set_state(AdminRequestStates.waiting_for_workers)
    await state.update_data(selected_worker_ids=[], use_all_workers=False)
    workers = await UserService(session).list_workers_for_actor(actor, company_id)
    await message.answer(
        await _build_workers_selection_text(actor, session, company_id, set()),
        reply_markup=build_admin_request_workers_keyboard(
            workers,
            set(),
            actor.ui_language,
            allow_confirm=False,
            allow_skip=True,
        ),
    )


async def _show_worker_selection_callback(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    actor: User,
) -> None:
    company_id = await _extract_company_id(state)
    if company_id is None:
        return

    await state.set_state(AdminRequestStates.waiting_for_workers)
    await state.update_data(selected_worker_ids=[], use_all_workers=False)
    workers = await UserService(session).list_workers_for_actor(actor, company_id)
    await _show_text_message(
        message,
        await _build_workers_selection_text(actor, session, company_id, set()),
        reply_markup=build_admin_request_workers_keyboard(
            workers,
            set(),
            actor.ui_language,
            allow_confirm=False,
            allow_skip=True,
        ),
    )


async def _build_workers_selection_text(
    actor: User,
    session: AsyncSession,
    company_id: int,
    selected_ids: set[int],
) -> str:
    company = await CompanyService(session).get_company(company_id)
    company_name = company.name if company is not None else str(company_id)
    lines = [
        t(actor.ui_language, "admin_request_select_workers"),
        "",
        f"🏢 <b>{escape(company_name)}</b>",
        t(actor.ui_language, "admin_request_workers_selected", count=len(selected_ids)),
    ]

    workers = await UserService(session).list_workers_for_actor(actor, company_id)
    if not workers:
        lines.extend(["", t(actor.ui_language, "admin_request_workers_empty")])

    return "\n".join(lines)


async def _build_confirmation_text(
    actor: User,
    state: FSMContext,
    workers: list[User],
    session: AsyncSession,
) -> str:
    data = await state.get_data()
    company_id = int(data.get("company_id"))
    company = await CompanyService(session).get_company(company_id)
    use_all_workers = bool(data.get("use_all_workers", False))
    if use_all_workers and workers:
        worker_names = t(actor.ui_language, "admin_request_all_workers")
    elif workers:
        worker_names = ", ".join(escape(worker.display_name) for worker in workers)
    else:
        worker_names = t(actor.ui_language, "admin_request_no_workers_assigned")
    flow_mode = str(data.get("flow_mode", "create"))

    lines = [
        t(actor.ui_language, "admin_request_confirm_title"),
        "",
        f"🏢 <b>{escape(company.name if company is not None else str(company_id))}</b>",
    ]
    if flow_mode == "create":
        lines.extend(
            [
                f"{t(actor.ui_language, 'request_new_phone')}: <b>{escape(str(data.get('phone', '')))}</b>",
                f"{t(actor.ui_language, 'request_new_problem')}: <b>{escape(str(data.get('problem_text', '')))}</b>",
                f"{t(actor.ui_language, 'request_detail_image') if data.get('problem_image') else t(actor.ui_language, 'skip')}",
            ]
        )
    else:
        lines.append(t(actor.ui_language, "request_assign_workers"))

    lines.append(f"{t(actor.ui_language, 'worker_assigned_label')}: <b>{worker_names}</b>")
    return "\n".join(lines)


async def _notify_workers_assigned(bot, request: Request) -> None:
    translator = TranslationService()
    creator_name = request.creator_admin.display_name if request.creator_admin is not None else "-"
    for worker in request.assigned_workers:
        translated_problem = await translator.translate_text(request.problem_text, worker.ui_language)
        translated_address = await translator.translate_text(request.address or "", worker.ui_language)
        text = "\n".join(
            [
                t(worker.ui_language, "worker_assigned_realtime"),
                f"{t(worker.ui_language, 'admin_request_creator')}: <b>{escape(creator_name)}</b>",
                f"{t(worker.ui_language, 'request_detail_status')}: <b>{RequestService.format_status(request.status, worker.ui_language)}</b>",
                f"{t(worker.ui_language, 'request_new_phone')}: <b>{escape(request.phone)}</b>",
                f"{t(worker.ui_language, 'request_new_problem')}: <b>{escape(translated_problem)}</b>",
                f"{t(worker.ui_language, 'request_new_address')}: <b>{escape(translated_address or t(worker.ui_language, 'request_no_address'))}</b>",
            ]
        )
        try:
            if request.problem_image:
                await bot.send_photo(
                    chat_id=worker.telegram_id,
                    photo=request.problem_image,
                    caption=text,
                    reply_markup=build_worker_assignment_message_keyboard(request.id, language=worker.ui_language),
                )
            else:
                await bot.send_message(
                    chat_id=worker.telegram_id,
                    text=text,
                    reply_markup=build_worker_assignment_message_keyboard(request.id, language=worker.ui_language),
                )
        except Exception:
            continue


async def _show_request_result(
    message: Message,
    request: Request,
    actor: User,
    *,
    prefix_text: str,
) -> None:
    detail_text = await _format_request_detail(request, actor)
    body = f"{prefix_text}\n\n{detail_text}" if prefix_text else detail_text
    keyboard = build_request_admin_actions_keyboard(
        request,
        actor.ui_language,
        can_reject=actor.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN},
        can_assign_workers=actor.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN},
    )
    if request.problem_image:
        await _safe_clear_reply_markup(message)
        try:
            await message.answer_photo(request.problem_image, caption=body, reply_markup=keyboard)
            return
        except TelegramBadRequest:
            pass

    await _show_text_message(message, body, reply_markup=keyboard)


async def _format_request_detail(request: Request, actor: User) -> str:
    translator = TranslationService()
    language = actor.ui_language
    problem_text = await translator.translate_text(request.problem_text, language)
    address_text = await translator.translate_text(request.address or "", language)
    creator = request.creator_admin.display_name if request.creator_admin is not None else "-"
    assigned_workers = ", ".join(escape(worker.display_name) for worker in request.assigned_workers) or "-"
    accepted_by = request.accepted_by_worker.display_name if request.accepted_by_worker is not None else "-"
    completed_by = request.completed_by_worker.display_name if request.completed_by_worker is not None else "-"
    owner = request.user.display_name if request.user is not None else "-"

    lines = [
        f"<b>{t(language, 'request_detail_title', request_id=request.id)}</b>",
        f"{t(language, 'request_detail_source')}: <b>{t(language, 'request_source_admin' if request.source_type.value == 'admin' else 'request_source_user')}</b>",
        f"{t(language, 'request_detail_status')}: <b>{RequestService.format_status(request.status, language)}</b>",
        f"{t(language, 'request_new_user')}: <b>{escape(owner)}</b>",
        f"{t(language, 'request_detail_created_by')}: <b>{escape(creator)}</b>",
        f"{t(language, 'request_new_phone')}: <b>{escape(request.phone)}</b>",
        f"{t(language, 'request_new_problem')}: <b>{escape(problem_text)}</b>",
        f"{t(language, 'request_new_address')}: <b>{escape(address_text or t(language, 'request_no_address'))}</b>",
        f"{t(language, 'request_detail_assigned_workers')}: <b>{assigned_workers}</b>",
        f"{t(language, 'request_detail_accepted_by_worker')}: <b>{escape(accepted_by)}</b>",
        f"{t(language, 'request_detail_completed_by_worker')}: <b>{escape(completed_by)}</b>",
    ]
    if request.problem_image:
        lines.append(t(language, "request_detail_image"))
    return "\n".join(lines)


async def _extract_company_id(state: FSMContext) -> int | None:
    company_id = (await state.get_data()).get("company_id")
    return company_id if isinstance(company_id, int) else None


async def _extract_selected_worker_ids(state: FSMContext) -> list[int]:
    selected = (await state.get_data()).get("selected_worker_ids", [])
    return [int(item) for item in selected if isinstance(item, int)]


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
    return user


async def _register_and_get_user(
    telegram_user: AiogramUser,
    session: AsyncSession,
) -> User:
    user_service = UserService(session)
    registration = await user_service.register_or_update(TelegramUserDTO.from_aiogram_user(telegram_user))
    return registration.user


async def _show_text_message(message: Message, text: str, reply_markup=None) -> None:
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
