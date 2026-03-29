from __future__ import annotations

from aiogram import Router

from app.bot.handlers.language import router as language_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.super_admin import router as super_admin_router


def setup_routers() -> Router:
    root_router = Router(name=__name__)
    root_router.include_router(start_router)
    root_router.include_router(language_router)
    root_router.include_router(super_admin_router)
    return root_router
