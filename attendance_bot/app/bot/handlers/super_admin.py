from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.reply.super_admin import (
    build_super_admin_keyboard,
    companies_button_labels,
    settings_button_labels,
    statistics_button_labels,
)
from app.domain.dto.user_dto import UserDTO
from app.domain.exceptions.auth_exceptions import AccessDeniedError
from app.services import build_super_admin_service


router = Router(name=__name__)


async def _resolve_super_admin(
    message: Message,
    *,
    session: AsyncSession,
    current_user: UserDTO | None,
) -> UserDTO | None:
    service = build_super_admin_service(session)
    try:
        return service.require_super_admin(current_user)
    except AccessDeniedError:
        await message.answer(
            service.access_denied(current_user.language if current_user else None),
            reply_markup=ReplyKeyboardRemove(),
        )
        return None


@router.message(F.text.in_(companies_button_labels()))
async def companies_handler(
    message: Message,
    session: AsyncSession,
    current_user: UserDTO | None,
) -> None:
    user = await _resolve_super_admin(message, session=session, current_user=current_user)
    if user is None or user.language is None:
        return

    service = build_super_admin_service(session)
    await message.answer(
        service.companies_placeholder(user.language),
        reply_markup=build_super_admin_keyboard(user.language),
    )


@router.message(F.text.in_(statistics_button_labels()))
async def statistics_handler(
    message: Message,
    session: AsyncSession,
    current_user: UserDTO | None,
) -> None:
    user = await _resolve_super_admin(message, session=session, current_user=current_user)
    if user is None or user.language is None:
        return

    service = build_super_admin_service(session)
    await message.answer(
        service.statistics_placeholder(user.language),
        reply_markup=build_super_admin_keyboard(user.language),
    )


@router.message(F.text.in_(settings_button_labels()))
async def settings_handler(
    message: Message,
    session: AsyncSession,
    current_user: UserDTO | None,
) -> None:
    user = await _resolve_super_admin(message, session=session, current_user=current_user)
    if user is None or user.language is None:
        return

    service = build_super_admin_service(session)
    await message.answer(
        service.settings_placeholder(user.language),
        reply_markup=build_super_admin_keyboard(user.language),
    )
