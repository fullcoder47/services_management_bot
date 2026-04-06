from aiogram.fsm.state import State, StatesGroup


class AdminRequestStates(StatesGroup):
    waiting_for_company = State()
    waiting_for_problem = State()
    waiting_for_phone = State()
    waiting_for_image = State()
    waiting_for_workers = State()
    waiting_for_confirmation = State()
