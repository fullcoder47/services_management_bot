from aiogram import Dispatcher

from .company import router as company_router
from .start import router as start_router


def register_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(start_router)
    dispatcher.include_router(company_router)
