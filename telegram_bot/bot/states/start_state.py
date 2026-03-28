from aiogram.fsm.state import State, StatesGroup


class StartStates(StatesGroup):
    waiting_for_phone = State()
