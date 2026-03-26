from aiogram.fsm.state import State, StatesGroup


class RequestCreateStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_problem = State()
    waiting_for_image = State()


class RequestDoneStates(StatesGroup):
    waiting_for_result_text = State()
    waiting_for_result_image = State()
    waiting_for_confirmation = State()
