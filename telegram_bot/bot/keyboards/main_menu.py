from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/start"), KeyboardButton(text="Kompaniyalar")],
        ],
        resize_keyboard=True,
    )
