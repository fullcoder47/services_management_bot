from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def build_main_menu(*, is_super_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton(text="/start")]]

    if is_super_admin:
        keyboard[0].append(KeyboardButton(text="Kompaniyalar"))
        keyboard.append([KeyboardButton(text="👤 Adminlar")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )
