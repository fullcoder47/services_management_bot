from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import User as AiogramUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, UserRole


class UserServiceError(Exception):
    pass


class UserNotFoundError(UserServiceError):
    pass


class UserRoleChangeError(UserServiceError):
    pass


@dataclass(slots=True)
class TelegramUserDTO:
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None
    is_bot: bool

    @classmethod
    def from_aiogram_user(cls, user: AiogramUser) -> "TelegramUserDTO":
        return cls(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            is_bot=user.is_bot,
        )


@dataclass(slots=True)
class UserRegistrationResult:
    user: User
    created: bool


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_or_update(self, telegram_user: TelegramUserDTO) -> UserRegistrationResult:
        existing_user = await self._get_by_telegram_id(telegram_user.telegram_id)
        if existing_user is not None:
            self._sync_user(existing_user, telegram_user)
            await self._session.commit()
            await self._session.refresh(existing_user)
            return UserRegistrationResult(user=existing_user, created=False)

        role = await self._resolve_role_for_new_user()
        new_user = User(
            telegram_id=telegram_user.telegram_id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
            is_bot=telegram_user.is_bot,
            role=role,
        )

        self._session.add(new_user)
        await self._session.commit()
        await self._session.refresh(new_user)
        return UserRegistrationResult(user=new_user, created=True)

    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self._get_by_telegram_id(telegram_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.get_user_by_telegram_id(telegram_id)

    async def get_users_by_company(self, company_id: int) -> list[User]:
        statement = select(User).where(User.company_id == company_id).order_by(User.id.asc())
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def assign_user_to_company(self, user_id: int, company_id: int, role: UserRole) -> User:
        if role == UserRole.SUPER_ADMIN:
            raise UserRoleChangeError("Super admin rolini bu yerda o'zgartirib bo'lmaydi.")

        user = await self._get_by_telegram_id(user_id)
        if user is None:
            user = User(
                telegram_id=user_id,
                username=None,
                first_name=f"Foydalanuvchi {user_id}",
                last_name=None,
                language_code=None,
                is_bot=False,
                role=role,
                company_id=company_id,
            )
            self._session.add(user)
            await self._session.commit()
            await self._session.refresh(user)
            return user

        if user.is_super_admin:
            raise UserRoleChangeError("Super admin foydalanuvchini boshqa rolga o'zgartirib bo'lmaydi.")

        user.company_id = company_id
        user.role = role
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def assign_company(self, telegram_id: int, company_id: int | None) -> User:
        user = await self._get_by_telegram_id(telegram_id)
        if user is None:
            raise UserNotFoundError("Foydalanuvchi topilmadi. Avval botga /start yuborishi kerak.")

        if user.is_super_admin and company_id is not None:
            raise UserRoleChangeError("Super adminni kompaniyaga biriktirib bo'lmaydi.")

        user.company_id = company_id
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def _get_by_telegram_id(self, telegram_id: int) -> User | None:
        statement = select(User).where(User.telegram_id == telegram_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def _resolve_role_for_new_user(self) -> UserRole:
        statement = select(func.count(User.id)).where(User.role == UserRole.SUPER_ADMIN)
        result = await self._session.execute(statement)
        total_super_admins = result.scalar_one()
        return UserRole.SUPER_ADMIN if total_super_admins == 0 else UserRole.USER

    @staticmethod
    def _sync_user(db_user: User, telegram_user: TelegramUserDTO) -> None:
        db_user.username = telegram_user.username
        db_user.first_name = telegram_user.first_name
        db_user.last_name = telegram_user.last_name
        db_user.language_code = telegram_user.language_code
        db_user.is_bot = telegram_user.is_bot
