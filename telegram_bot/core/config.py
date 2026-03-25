from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(slots=True)
class Settings:
    bot_token: str
    database_url: str


def _normalize_database_url(database_url: str) -> str:
    sqlite_prefix = "sqlite+aiosqlite:///./"
    if database_url.startswith(sqlite_prefix):
        db_name = database_url.removeprefix(sqlite_prefix)
        return f"sqlite+aiosqlite:///{(BASE_DIR / db_name).as_posix()}"
    return database_url


def load_settings() -> Settings:
    _load_dotenv(BASE_DIR / ".env")

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        msg = "BOT_TOKEN topilmadi. .env.example faylidan nusxa olib, .env ichiga Telegram bot tokenini kiriting."
        raise RuntimeError(msg)

    database_url = _normalize_database_url(
        os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db").strip()
    )
    return Settings(bot_token=bot_token, database_url=database_url)
