from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.domain.enums.language import Language
from app.domain.enums.role import Role


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        query = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def exists_by_telegram_id(self, telegram_id: int) -> bool:
        query = select(User.id).where(User.telegram_id == telegram_id).limit(1)
        return await self.session.scalar(query) is not None

    async def create(
        self,
        *,
        telegram_id: int,
        full_name: str,
        username: str | None,
        phone: str | None,
        role: Role,
        language: Language | None,
        is_active: bool,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            phone=phone,
            role=role,
            language=language,
            is_active=is_active,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def update_language(self, user: User, language: Language) -> User:
        user.language = language
        await self.session.flush()
        return user

    async def update_last_known_fields(
        self,
        user: User,
        *,
        full_name: str,
        username: str | None,
    ) -> User:
        user.full_name = full_name
        user.username = username
        await self.session.flush()
        return user

    async def update_role(self, user: User, role: Role) -> User:
        user.role = role
        await self.session.flush()
        return user

    async def update_is_active(self, user: User, is_active: bool) -> User:
        user.is_active = is_active
        await self.session.flush()
        return user
