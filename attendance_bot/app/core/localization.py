from __future__ import annotations

from app.domain.enums.language import Language


def resolve_language(lang: Language | str | None) -> Language:
    if isinstance(lang, Language):
        return lang
    if isinstance(lang, str):
        try:
            return Language(lang)
        except ValueError:
            return Language.EN
    return Language.EN


def t(lang: Language | str | None, *, uz: str, ru: str, en: str) -> str:
    language = resolve_language(lang)
    if language is Language.UZ:
        return uz
    if language is Language.RU:
        return ru
    return en


def language_label(language: Language) -> str:
    return {
        Language.UZ: "🇺🇿 O'zbekcha",
        Language.RU: "🇷🇺 Русский",
        Language.EN: "🇬🇧 English",
    }[language]
