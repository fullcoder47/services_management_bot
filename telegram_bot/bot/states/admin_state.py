from aiogram.fsm.state import State, StatesGroup


class AdminAssignStates(StatesGroup):
    waiting_for_company = State()
    waiting_for_user_id = State()
    waiting_for_role = State()
