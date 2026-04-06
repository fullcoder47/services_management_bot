from aiogram.fsm.state import State, StatesGroup


class WorkerDoneStates(StatesGroup):
    waiting_for_result_text = State()
    waiting_for_result_image = State()
    waiting_for_confirmation = State()


class WorkersAdminStates(StatesGroup):
    waiting_for_company = State()
    waiting_for_user_id = State()
