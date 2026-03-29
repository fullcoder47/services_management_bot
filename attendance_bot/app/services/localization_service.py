from __future__ import annotations

from app.core.localization import t
from app.domain.enums.language import Language


class LocalizationService:
    def select_language_prompt(self) -> str:
        return "Tilni tanlang / Выберите язык / Choose a language."

    def language_saved(self, language: Language) -> str:
        return t(
            language,
            uz="Til muvaffaqiyatli tanlandi.",
            ru="Язык успешно сохранен.",
            en="Language was saved successfully.",
        )

    def access_denied(self, language: Language | None) -> str:
        return t(
            language,
            uz="Sizda ushbu botdan foydalanish huquqi yo'q.",
            ru="У вас нет доступа к этому боту.",
            en="You do not have access to this bot.",
        )

    def language_saved_and_denied(self, language: Language) -> str:
        return "\n\n".join(
            [
                self.language_saved(language),
                self.access_denied(language),
            ]
        )

    def super_admin_welcome(self, language: Language, full_name: str) -> str:
        return t(
            language,
            uz=f"Super admin paneliga xush kelibsiz, {full_name}.\nKerakli bo'limni tanlang.",
            ru=f"Добро пожаловать в панель super admin, {full_name}.\nВыберите нужный раздел.",
            en=f"Welcome to the super admin panel, {full_name}.\nChoose the section you need.",
        )

    def companies_button(self, language: Language) -> str:
        return t(language, uz="🏢 Kompaniyalar", ru="🏢 Компании", en="🏢 Companies")

    def statistics_button(self, language: Language) -> str:
        return t(language, uz="📊 Statistika", ru="📊 Статистика", en="📊 Statistics")

    def settings_button(self, language: Language) -> str:
        return t(language, uz="⚙️ Sozlamalar", ru="⚙️ Настройки", en="⚙️ Settings")

    def companies_placeholder(self, language: Language) -> str:
        return t(
            language,
            uz="Kompaniyalar moduli keyingi bosqichda qo'shiladi.",
            ru="Модуль компаний будет добавлен на следующем этапе.",
            en="The companies module will be added in the next phase.",
        )

    def statistics_placeholder(self, language: Language) -> str:
        return t(
            language,
            uz="Statistika moduli keyingi bosqichda qo'shiladi.",
            ru="Модуль статистики будет добавлен на следующем этапе.",
            en="The statistics module will be added in the next phase.",
        )

    def settings_placeholder(self, language: Language) -> str:
        return t(
            language,
            uz="Sozlamalar bo'limi tayyorlanmoqda.\nTilni almashtirish stubi keyingi bosqichda shu yerga ulanadi.",
            ru="Раздел настроек готовится.\nЗаглушка смены языка будет подключена сюда на следующем этапе.",
            en="The settings section is being prepared.\nA change-language stub will be connected here in the next phase.",
        )
