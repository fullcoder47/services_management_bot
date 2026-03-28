from __future__ import annotations

from urllib.parse import quote

from aiohttp import ClientError, ClientSession

from db.models import UserLanguage


class TranslationService:
    GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

    async def translate_text(
        self,
        text: str,
        target_language: UserLanguage,
    ) -> str:
        normalized_text = text.strip()
        if not normalized_text:
            return text

        query = (
            f"{self.GOOGLE_TRANSLATE_URL}?client=gtx&sl=auto&tl={target_language.value}"
            f"&dt=t&q={quote(normalized_text)}"
        )

        try:
            async with ClientSession() as session:
                async with session.get(query, timeout=10) as response:
                    if response.status != 200:
                        return text
                    payload = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError):
            return text

        try:
            translated_chunks = [chunk[0] for chunk in payload[0] if chunk and chunk[0]]
        except (TypeError, IndexError):
            return text

        translated_text = "".join(translated_chunks).strip()
        return translated_text or text
