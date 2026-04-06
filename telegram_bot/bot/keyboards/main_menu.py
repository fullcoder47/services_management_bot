from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from db.models import UserLanguage, UserRole
from services.i18n import t


def build_main_menu(*, role: UserRole, has_company: bool, language: UserLanguage) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = [[KeyboardButton(text="/start")]]

    if role == UserRole.SUPER_ADMIN:
        keyboard[0].append(KeyboardButton(text=t(language, "menu_companies")))
        keyboard.append([KeyboardButton(text=t(language, "menu_admins"))])
        keyboard.append(
            [
                KeyboardButton(text=t(language, "menu_requests")),
                KeyboardButton(text=t(language, "menu_create_request")),
            ]
        )
        keyboard.append(
            [
                KeyboardButton(text=t(language, "menu_workers")),
                KeyboardButton(text=t(language, "menu_users")),
            ]
        )
        keyboard.append([KeyboardButton(text=t(language, "menu_broadcast"))])
        keyboard.append([KeyboardButton(text=t(language, "menu_help"))])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    if role == UserRole.ADMIN:
        keyboard.append(
            [
                KeyboardButton(text=t(language, "menu_requests")),
                KeyboardButton(text=t(language, "menu_create_request")),
            ]
        )
        keyboard.append(
            [
                KeyboardButton(text=t(language, "menu_workers")),
                KeyboardButton(text=t(language, "menu_users")),
            ]
        )
        keyboard.append([KeyboardButton(text=t(language, "menu_broadcast"))])
        keyboard.append([KeyboardButton(text=t(language, "menu_help"))])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    if role == UserRole.OPERATOR:
        keyboard.append([KeyboardButton(text=t(language, "menu_requests"))])
        keyboard.append([KeyboardButton(text=t(language, "menu_help"))])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    if role == UserRole.WORKER:
        keyboard.append([KeyboardButton(text=t(language, "menu_worker_assigned"))])
        keyboard.append(
            [
                KeyboardButton(text=t(language, "menu_worker_in_progress")),
                KeyboardButton(text=t(language, "menu_worker_done")),
            ]
        )
        keyboard.append([KeyboardButton(text=t(language, "menu_help"))])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    if has_company:
        keyboard.append([KeyboardButton(text=t(language, "menu_leave_request"))])
        keyboard.append([KeyboardButton(text=t(language, "menu_my_requests"))])

    keyboard.append([KeyboardButton(text=t(language, "menu_help"))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
