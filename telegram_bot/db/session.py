from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.base import Base
from db.models import Company, Request, User  # noqa: F401


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
        if "users" in table_names:
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "company_id" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN company_id INTEGER"))
            if "phone_number" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(32)"))
            if "preferred_language" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN preferred_language VARCHAR(8)"))

            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_users_company_id ON users (company_id)")
            )

        if "requests" in table_names:
            request_columns = {column["name"] for column in inspector.get_columns("requests")}
            if "status" not in request_columns:
                connection.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN status VARCHAR(32) "
                        "NOT NULL DEFAULT 'pending'"
                    )
                )
            if "result_text" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN result_text TEXT"))
            if "result_image" not in request_columns:
                connection.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN result_image VARCHAR(512) "
                        "NOT NULL DEFAULT ''"
                    )
                )
            if "completed_at" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN completed_at DATETIME"))
            if "company_id" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN company_id INTEGER"))
            if "problem_image" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN problem_image VARCHAR(512)"))
            if "address" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN address TEXT"))

            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requests_user_id ON requests (user_id)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requests_company_id ON requests (company_id)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requests_status ON requests (status)")
            )
