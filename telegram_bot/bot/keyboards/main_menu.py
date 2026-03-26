from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from db.models import UserRole


def build_main_menu(*, role: UserRole, has_company: bool) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = [[KeyboardButton(text="/start")]]

    if role == UserRole.SUPER_ADMIN:
        keyboard[0].append(KeyboardButton(text="Kompaniyalar"))
        keyboard.append([KeyboardButton(text="👤 Adminlar")])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    if has_company:
        keyboard[0].append(KeyboardButton(text="📝 Ariza qoldirish"))

    if role in {UserRole.ADMIN, UserRole.OPERATOR}:
        keyboard.append([KeyboardButton(text="📥 Arizalar")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
