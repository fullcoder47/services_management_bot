from __future__ import annotations

from app.core.localization import t
from app.domain.enums.language import Language


class LocalizationService:
    def select_language_prompt(self) -> str:
        return t(
            None,
            uz="Tilni tanlang / Выберите язык / Choose a language.",
            ru="Tilni tanlang / Выберите язык / Choose a language.",
            en="Tilni tanlang / Выберите язык / Choose a language.",
        )

    def language_saved(self, language: Language) -> str:
        return t(
            language,
            uz="Til muvaffaqiyatli tanlandi.",
            ru="Язык успешно сохранен.",
            en="Language was saved successfully.",
        )

    def language_saved_and_denied(self, language: Language) -> str:
        return t(
            language,
            uz="Til muvaffaqiyatli tanlandi.\n\nSizda ushbu botdan foydalanish huquqi yo'q.",
            ru="Язык успешно сохранен.\n\nУ вас нет доступа к этому боту.",
            en="Language was saved successfully.\n\nYou do not have access to this bot.",
        )

    def access_denied(self, language: Language | None) -> str:
        return t(
            language,
            uz="Sizda ushbu botdan foydalanish huquqi yo'q.",
            ru="У вас нет доступа к этому боту.",
            en="You do not have access to this bot.",
        )

    def super_admin_panel(self, *, language: Language, full_name: str) -> str:
        return t(
            language,
            uz=f"Super admin paneliga xush kelibsiz, {full_name}.\nKerakli bo'limni tanlang.",
            ru=f"Добро пожаловать в панель super admin, {full_name}.\nВыберите нужный раздел.",
            en=f"Welcome to the super admin panel, {full_name}.\nChoose the section you need.",
        )

    def companies_button(self, language: Language) -> str:
        return t(
            language,
            uz="🏢 Kompaniyalar",
            ru="🏢 Компании",
            en="🏢 Companies",
        )

    def statistics_button(self, language: Language) -> str:
        return t(
            language,
            uz="📊 Statistika",
            ru="📊 Статистика",
            en="📊 Statistics",
        )

    def settings_button(self, language: Language) -> str:
        return t(
            language,
            uz="⚙️ Sozlamalar",
            ru="⚙️ Настройки",
            en="⚙️ Settings",
        )

    def companies_placeholder(self, language: Language) -> str:
        return t(
            language,
            uz="Kompaniyalar bo'limi keyingi bosqichda ochiladi.",
            ru="Раздел компаний будет добавлен на следующем этапе.",
            en="The companies section will be added in the next phase.",
        )

    def statistics_placeholder(self, language: Language) -> str:
        return t(
            language,
            uz="Statistika bo'limi keyingi bosqichda qo'shiladi.",
            ru="Раздел статистики будет добавлен на следующем этапе.",
            en="The statistics section will be added in the next phase.",
        )

    def settings_placeholder(self, language: Language) -> str:
        return t(
            language,
            uz="Sozlamalar bo'limi tayyorlanmoqda.\nTilni almashtirish oqimi keyingi bosqichda shu yerga qo'shiladi.",
            ru="Раздел настроек готовится.\nСмена языка будет добавлена сюда на следующем этапе.",
            en="The settings section is being prepared.\nThe language change flow will be added here in the next phase.",
        )
