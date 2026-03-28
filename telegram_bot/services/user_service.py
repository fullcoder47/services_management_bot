from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re

from aiogram.types import User as AiogramUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Company, User, UserLanguage, UserRole


class UserServiceError(Exception):
    pass


class UserNotFoundError(UserServiceError):
    pass


class UserRoleChangeError(UserServiceError):
    pass


class UserAccessError(UserServiceError):
    pass


class UserValidationError(UserServiceError):
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


@dataclass(slots=True)
class CompanyAdminContacts:
    company: Company
    admins: list[User]


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

    async def list_users_for_actor(self, actor: User) -> list[User]:
        if actor.is_super_admin:
            statement = (
                select(User)
                .options(selectinload(User.company))
                .order_by(
                    User.company_id.asc(),
                    User.role.asc(),
                    User.id.asc(),
                )
            )
            result = await self._session.execute(statement)
            return list(result.scalars().all())

        if actor.role == UserRole.ADMIN and actor.company_id is not None:
            statement = (
                select(User)
                .options(selectinload(User.company))
                .where(User.company_id == actor.company_id)
                .order_by(User.id.asc())
            )
            result = await self._session.execute(statement)
            return list(result.scalars().all())

        raise UserAccessError("Bu bo'lim faqat super admin va admin uchun.")

    async def get_broadcast_recipients(
        self,
        actor: User,
        target: str = "all",
    ) -> list[User]:
        if actor.is_super_admin:
            statement = select(User).where(User.role != UserRole.SUPER_ADMIN).where(User.id != actor.id)
            if target == "admins":
                statement = statement.where(User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]))
            elif target == "users":
                statement = statement.where(User.role == UserRole.USER)
            elif target != "all":
                raise UserAccessError("Xabar qabul qiluvchilari noto'g'ri tanlangan.")

            statement = statement.order_by(User.company_id.asc(), User.id.asc())
            result = await self._session.execute(statement)
            return list(result.scalars().all())

        if actor.role == UserRole.ADMIN and actor.company_id is not None:
            statement = (
                select(User)
                .where(User.company_id == actor.company_id, User.id != actor.id)
                .order_by(User.id.asc())
            )
            result = await self._session.execute(statement)
            return list(result.scalars().all())

        raise UserAccessError("Xabar yuborish faqat super admin va admin uchun.")

    async def get_management_users_by_company_ids(
        self,
        company_ids: list[int],
    ) -> dict[int, dict[UserRole, list[User]]]:
        if not company_ids:
            return {}

        statement = (
            select(User)
            .where(
                User.company_id.in_(company_ids),
                User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]),
            )
            .order_by(User.company_id.asc(), User.role.asc(), User.id.asc())
        )
        result = await self._session.execute(statement)

        summary: dict[int, dict[UserRole, list[User]]] = defaultdict(
            lambda: {
                UserRole.ADMIN: [],
                UserRole.OPERATOR: [],
            }
        )
        for user in result.scalars().all():
            if user.company_id is None:
                continue
            summary[user.company_id][user.role].append(user)

        return dict(summary)

    async def get_company_admin_contacts(self) -> list[CompanyAdminContacts]:
        statement = (
            select(Company)
            .options(selectinload(Company.users))
            .order_by(Company.name.asc(), Company.id.asc())
        )
        result = await self._session.execute(statement)
        companies = list(result.scalars().all())

        contacts: list[CompanyAdminContacts] = []
        for company in companies:
            admins = sorted(
                [user for user in company.users if user.role == UserRole.ADMIN],
                key=lambda user: (user.first_name.lower(), user.id),
            )
            contacts.append(CompanyAdminContacts(company=company, admins=admins))

        return contacts

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

    async def update_phone_number(self, telegram_id: int, phone_number: str) -> User:
        user = await self._get_by_telegram_id(telegram_id)
        if user is None:
            raise UserNotFoundError("Foydalanuvchi topilmadi. Avval /start yuboring.")

        normalized_phone = self.normalize_phone_number(phone_number)
        user.phone_number = normalized_phone
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_preferred_language(
        self,
        telegram_id: int,
        language: UserLanguage,
    ) -> User:
        user = await self._get_by_telegram_id(telegram_id)
        if user is None:
            raise UserNotFoundError("Foydalanuvchi topilmadi. Avval /start yuboring.")

        user.preferred_language = language
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

    async def select_company_for_user(self, telegram_id: int, company_id: int) -> User:
        user = await self._get_by_telegram_id(telegram_id)
        if user is None:
            raise UserNotFoundError("Foydalanuvchi topilmadi. Avval /start yuboring.")

        if user.is_super_admin:
            raise UserRoleChangeError("Super admin kompaniya tanlamaydi.")

        if user.role in {UserRole.ADMIN, UserRole.OPERATOR}:
            raise UserRoleChangeError("Admin yoki operator kompaniyani o'zi tanlay olmaydi.")

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
    def normalize_phone_number(phone_number: str) -> str:
        raw_value = phone_number.strip()
        if not raw_value:
            raise UserValidationError("Telefon raqami majburiy.")

        normalized = re.sub(r"[^\d+]", "", raw_value)
        if normalized.count("+") > 1 or ("+" in normalized and not normalized.startswith("+")):
            raise UserValidationError("Telefon raqami noto'g'ri formatda.")

        digits_only = normalized[1:] if normalized.startswith("+") else normalized
        if not digits_only.isdigit() or len(digits_only) < 7 or len(digits_only) > 15:
            raise UserValidationError("Telefon raqami noto'g'ri formatda.")

        return f"+{digits_only}" if normalized.startswith("+") else digits_only

    @staticmethod
    def _sync_user(db_user: User, telegram_user: TelegramUserDTO) -> None:
        db_user.username = telegram_user.username
        db_user.first_name = telegram_user.first_name
        db_user.last_name = telegram_user.last_name
        db_user.language_code = telegram_user.language_code
        db_user.is_bot = telegram_user.is_bot
