from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from db.models import UserRole


def build_main_menu(*, role: UserRole, has_company: bool) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = [[KeyboardButton(text="/start")]]

    if role == UserRole.SUPER_ADMIN:
        keyboard[0].append(KeyboardButton(text="Kompaniyalar"))
        keyboard.append([KeyboardButton(text="👤 Adminlar")])
        keyboard.append([KeyboardButton(text="📩 Arizalar"), KeyboardButton(text="👥 Userlar")])
        keyboard.append([KeyboardButton(text="📢 Xabar yuborish")])
        keyboard.append([KeyboardButton(text="Yordam")])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    if role == UserRole.ADMIN:
        keyboard.append([KeyboardButton(text="📩 Arizalar"), KeyboardButton(text="👥 Userlar")])
        keyboard.append([KeyboardButton(text="📢 Xabar yuborish")])
        keyboard.append([KeyboardButton(text="Yordam")])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    if role == UserRole.OPERATOR:
        keyboard.append([KeyboardButton(text="📩 Arizalar")])
        keyboard.append([KeyboardButton(text="Yordam")])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    if has_company:
        keyboard.append([KeyboardButton(text="📨 Ariza qoldirish")])
        keyboard.append([KeyboardButton(text="📄 Mening arizalarim")])

    keyboard.append([KeyboardButton(text="Yordam")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
