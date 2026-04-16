from aiogram.fsm.state import State, StatesGroup


class CompanyChatStates(StatesGroup):
    waiting_for_message = State()
