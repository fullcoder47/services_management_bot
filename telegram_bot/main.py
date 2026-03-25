from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import register_routers
from bot.middlewares.db import DbSessionMiddleware
from core.config import Settings, load_settings
from core.logging import configure_logging
from db.session import Database


async def main() -> None:
    settings: Settings = load_settings()
    configure_logging()

    database = Database(settings.database_url)
    await database.create_models()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    dispatcher.update.middleware(DbSessionMiddleware(database.session_factory))
    register_routers(dispatcher)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
