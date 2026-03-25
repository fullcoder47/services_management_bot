from aiogram import Dispatcher

from .start import router as start_router


def register_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(start_router)
