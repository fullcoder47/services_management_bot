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

            Database._ensure_users_schema(connection)
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_users_company_id ON users (company_id)")
            )
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id)")
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
            if "source_type" not in request_columns:
                connection.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN source_type VARCHAR(32) "
                        "NOT NULL DEFAULT 'user'"
                    )
                )
            if "created_by_admin_id" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN created_by_admin_id INTEGER"))
            if "accepted_by_worker_id" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN accepted_by_worker_id INTEGER"))
            if "accepted_at" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN accepted_at DATETIME"))
            if "completed_by_worker_id" not in request_columns:
                connection.execute(text("ALTER TABLE requests ADD COLUMN completed_by_worker_id INTEGER"))

            Database._ensure_requests_schema(connection)
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requests_user_id ON requests (user_id)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requests_company_id ON requests (company_id)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requests_status ON requests (status)")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_requests_created_by_admin_id "
                    "ON requests (created_by_admin_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_requests_accepted_by_worker_id "
                    "ON requests (accepted_by_worker_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_requests_completed_by_worker_id "
                    "ON requests (completed_by_worker_id)"
                )
            )

        if "request_workers" not in table_names:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS request_workers ("
                    "request_id INTEGER NOT NULL, "
                    "worker_id INTEGER NOT NULL, "
                    "PRIMARY KEY (request_id, worker_id)"
                    ")"
                )
            )

        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_request_workers_request_id "
                "ON request_workers (request_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_request_workers_worker_id "
                "ON request_workers (worker_id)"
            )
        )

    @staticmethod
    def _get_table_sql(connection, table_name: str) -> str:
        row = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = :table_name"
            ),
            {"table_name": table_name},
        ).fetchone()
        if row is None or row[0] is None:
            return ""
        return str(row[0]).lower()

    @staticmethod
    def _ensure_users_schema(connection) -> None:
        table_sql = Database._get_table_sql(connection, "users")
        if "worker" in table_sql:
            return

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        try:
            connection.execute(
                text(
                    "CREATE TABLE users__new ("
                    "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                    "telegram_id BIGINT NOT NULL, "
                    "username VARCHAR(255), "
                    "first_name VARCHAR(255) NOT NULL, "
                    "last_name VARCHAR(255), "
                    "phone_number VARCHAR(32), "
                    "preferred_language VARCHAR(8), "
                    "language_code VARCHAR(32), "
                    "is_bot BOOLEAN NOT NULL DEFAULT 0, "
                    "is_active BOOLEAN NOT NULL DEFAULT 1, "
                    "company_id INTEGER, "
                    "role VARCHAR(32) NOT NULL DEFAULT 'user' "
                    "CHECK (role IN ('user', 'operator', 'worker', 'admin', 'super_admin')), "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE SET NULL"
                    ")"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO users__new ("
                    "id, telegram_id, username, first_name, last_name, phone_number, "
                    "preferred_language, language_code, is_bot, is_active, company_id, role, "
                    "created_at, updated_at"
                    ") "
                    "SELECT "
                    "id, telegram_id, username, first_name, last_name, phone_number, "
                    "CASE "
                    "WHEN preferred_language IN ('uz', 'ru', 'en') THEN preferred_language "
                    "ELSE NULL "
                    "END, "
                    "language_code, COALESCE(is_bot, 0), COALESCE(is_active, 1), company_id, "
                    "CASE "
                    "WHEN role IN ('user', 'operator', 'worker', 'admin', 'super_admin') THEN role "
                    "ELSE 'user' "
                    "END, "
                    "COALESCE(created_at, CURRENT_TIMESTAMP), "
                    "COALESCE(updated_at, CURRENT_TIMESTAMP) "
                    "FROM users"
                )
            )
            connection.execute(text("DROP TABLE users"))
            connection.execute(text("ALTER TABLE users__new RENAME TO users"))
        finally:
            connection.execute(text("PRAGMA foreign_keys=ON"))

    @staticmethod
    def _ensure_requests_schema(connection) -> None:
        table_sql = Database._get_table_sql(connection, "requests")
        if "assigned" in table_sql and "source_type" in table_sql:
            return

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        try:
            connection.execute(
                text(
                    "CREATE TABLE requests__new ("
                    "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                    "user_id INTEGER NOT NULL, "
                    "company_id INTEGER, "
                    "created_by_admin_id INTEGER, "
                    "accepted_by_worker_id INTEGER, "
                    "completed_by_worker_id INTEGER, "
                    "phone VARCHAR(32) NOT NULL, "
                    "problem_text TEXT NOT NULL, "
                    "address TEXT NOT NULL DEFAULT '', "
                    "problem_image VARCHAR(512), "
                    "source_type VARCHAR(32) NOT NULL DEFAULT 'user' "
                    "CHECK (source_type IN ('user', 'admin')), "
                    "status VARCHAR(32) NOT NULL DEFAULT 'pending' "
                    "CHECK (status IN ('pending', 'assigned', 'in_progress', 'done')), "
                    "accepted_at DATETIME, "
                    "result_text TEXT, "
                    "result_image VARCHAR(512) NOT NULL DEFAULT '', "
                    "completed_at DATETIME, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, "
                    "FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE SET NULL, "
                    "FOREIGN KEY(created_by_admin_id) REFERENCES users (id) ON DELETE SET NULL, "
                    "FOREIGN KEY(accepted_by_worker_id) REFERENCES users (id) ON DELETE SET NULL, "
                    "FOREIGN KEY(completed_by_worker_id) REFERENCES users (id) ON DELETE SET NULL"
                    ")"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO requests__new ("
                    "id, user_id, company_id, created_by_admin_id, accepted_by_worker_id, "
                    "completed_by_worker_id, phone, problem_text, address, problem_image, "
                    "source_type, status, accepted_at, result_text, result_image, completed_at, "
                    "created_at, updated_at"
                    ") "
                    "SELECT "
                    "id, user_id, company_id, created_by_admin_id, accepted_by_worker_id, "
                    "completed_by_worker_id, phone, problem_text, COALESCE(address, ''), problem_image, "
                    "CASE "
                    "WHEN source_type IN ('user', 'admin') THEN source_type "
                    "ELSE 'user' "
                    "END, "
                    "CASE "
                    "WHEN status IN ('pending', 'assigned', 'in_progress', 'done') THEN status "
                    "WHEN status = 'progress' THEN 'in_progress' "
                    "ELSE 'pending' "
                    "END, "
                    "accepted_at, result_text, COALESCE(result_image, ''), completed_at, "
                    "COALESCE(created_at, CURRENT_TIMESTAMP), "
                    "COALESCE(updated_at, CURRENT_TIMESTAMP) "
                    "FROM requests"
                )
            )
            connection.execute(text("DROP TABLE requests"))
            connection.execute(text("ALTER TABLE requests__new RENAME TO requests"))
        finally:
            connection.execute(text("PRAGMA foreign_keys=ON"))
