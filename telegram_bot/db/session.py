from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.base import Base
from db.models import Company, User  # noqa: F401


class Database:
    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(database_url, echo=False, future=True)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def create_models(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(self._run_sqlite_migrations)

    async def dispose(self) -> None:
        await self.engine.dispose()

    @staticmethod
    def _run_sqlite_migrations(connection) -> None:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "users" not in table_names:
            return

        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "company_id" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN company_id INTEGER"))

        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_company_id ON users (company_id)"))
