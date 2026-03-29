from __future__ import annotations

import socket

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.db.models import User  # noqa: F401


class DatabaseInitializationError(RuntimeError):
    """Raised when the database cannot be initialized."""


def create_engine_and_session_factory(
    settings: Settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        settings.db_url,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, session_factory


async def init_db(engine: AsyncEngine, settings: Settings) -> None:
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        raise DatabaseInitializationError(_build_database_error_message(settings, exc)) from exc


def _build_database_error_message(settings: Settings, exc: Exception) -> str:
    root_cause = _extract_root_cause(exc)
    host = settings.db_host or "unknown"
    base_message = f"Database connection failed for host '{host}'."

    if isinstance(root_cause, socket.gaierror):
        return (
            f"{base_message} Host could not be resolved.\n"
            "Agar Railway ishlatayotgan bo'lsangiz, local mashinada `*.railway.internal` emas, public hostdan foydalaning.\n"
            f"Current DB_URL: {settings.masked_db_url}"
        )

    if isinstance(root_cause, ConnectionRefusedError):
        return (
            f"{base_message} Connection was refused.\n"
            "PostgreSQL ishga tushganini, port ochiq ekanini va DB_URL to'g'ri ekanini tekshiring.\n"
            f"Current DB_URL: {settings.masked_db_url}"
        )

    if isinstance(root_cause, TimeoutError):
        return (
            f"{base_message} Connection timed out.\n"
            "Tarmoq, firewall yoki database host mavjudligini tekshiring.\n"
            f"Current DB_URL: {settings.masked_db_url}"
        )

    if isinstance(root_cause, OSError):
        return (
            f"{base_message} OS/network level error yuz berdi: {root_cause}.\n"
            f"Current DB_URL: {settings.masked_db_url}"
        )

    if isinstance(exc, SQLAlchemyError):
        return (
            f"{base_message} SQLAlchemy database initialization error yuz berdi.\n"
            f"Current DB_URL: {settings.masked_db_url}"
        )

    return f"{base_message} {root_cause}"


def _extract_root_cause(exc: Exception) -> BaseException:
    current: BaseException = exc
    visited: set[int] = set()

    while id(current) not in visited:
        visited.add(id(current))
        next_cause = current.__cause__ or current.__context__
        if next_cause is None:
            return current
        current = next_cause

    return current
