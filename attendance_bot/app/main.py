from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from pydantic import ValidationError

from app.bot.middlewares.auth import AuthContextMiddleware
from app.bot.middlewares.db import DBSessionMiddleware
from app.bot.routers import setup_routers
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import DatabaseInitializationError, create_engine_and_session_factory, init_db


async def run() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        settings = get_settings()
    except ValidationError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    engine, session_factory = create_engine_and_session_factory(settings)
    try:
        await init_db(engine, settings)
    except DatabaseInitializationError as exc:
        await engine.dispose()
        logger.error(str(exc))
        raise SystemExit(str(exc)) from exc

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    dispatcher.update.outer_middleware(DBSessionMiddleware(session_factory))
    dispatcher.message.middleware(AuthContextMiddleware())
    dispatcher.callback_query.middleware(AuthContextMiddleware())
    dispatcher.include_router(setup_routers())

    try:
        logger.info("Starting bot polling")
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot, settings=settings)
    finally:
        logger.info("Stopping bot")
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
