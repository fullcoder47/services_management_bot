from aiogram import Dispatcher

from .admin import router as admin_router
from .admin_requests import router as admin_requests_router
from .company import router as company_router
from .help import router as help_router
from .manager import router as manager_router
from .request import router as request_router
from .request_admin import router as request_admin_router
from .start import router as start_router
from .worker import router as worker_router
from .workers_admin import router as workers_admin_router


def register_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(start_router)
    dispatcher.include_router(help_router)
    dispatcher.include_router(request_router)
    dispatcher.include_router(admin_requests_router)
    dispatcher.include_router(worker_router)
    dispatcher.include_router(request_admin_router)
    dispatcher.include_router(manager_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(workers_admin_router)
    dispatcher.include_router(company_router)
