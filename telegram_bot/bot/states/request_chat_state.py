from aiogram.fsm.state import State, StatesGroup


class RequestChatStates(StatesGroup):
    waiting_for_message = State()
