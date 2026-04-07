from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    waiting_for_phone = State()
