from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Company, CompanyPlan, User
from services.user_service import UserService, UserValidationError


class CompanyServiceError(Exception):
    pass


class CompanyAlreadyExistsError(CompanyServiceError):
    pass


class CompanyNotFoundError(CompanyServiceError):
    pass


@dataclass(slots=True)
class CreateCompanyDTO:
    name: str
    dispatcher_phone: str
    plan: CompanyPlan


def normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value

    return value.astimezone(UTC).replace(tzinfo=None)


class CompanyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_companies(self) -> list[Company]:
        statement = select(Company).order_by(Company.id.asc())
        result = await self._session.execute(statement)
        companies = list(result.scalars().all())
        await self._sync_subscription_state(companies)
        return companies

    async def list_active_companies(self) -> list[Company]:
        companies = await self.list_companies()
        return [company for company in companies if self.check_access(company)]

    async def get_company(self, company_id: int) -> Company | None:
        statement = select(Company).where(Company.id == company_id)
        result = await self._session.execute(statement)
        company = result.scalar_one_or_none()
        if company is None:
            return None

        await self._sync_subscription_state([company])
        return company

    async def get_active_company(self, company_id: int) -> Company | None:
        company = await self.get_company(company_id)
        if company is None or not self.check_access(company):
            return None
        return company

    def check_access(self, company: Company) -> bool:
        subscription_end = normalize_utc_datetime(company.subscription_end)
        if subscription_end is None:
            return False

        return subscription_end > self._utcnow()

    async def create_company(self, payload: CreateCompanyDTO) -> Company:
        normalized_name = payload.name.strip()
        if not normalized_name:
            raise CompanyServiceError("Kompaniya nomi bo'sh bo'lishi mumkin emas.")

        try:
            normalized_dispatcher_phone = UserService.normalize_phone_number(
                payload.dispatcher_phone
            )
        except UserValidationError as exc:
            raise CompanyServiceError(str(exc)) from exc

        existing = await self._find_by_name(normalized_name)
        if existing is not None:
            raise CompanyAlreadyExistsError("Bu nomdagi kompaniya allaqachon mavjud.")

        company = Company(
            name=normalized_name,
            dispatcher_phone=normalized_dispatcher_phone,
            plan=payload.plan,
            is_active=False,
            subscription_end=None,
        )
        self._session.add(company)
        await self._session.commit()
        await self._session.refresh(company)
        company.subscription_end = normalize_utc_datetime(company.subscription_end)
        return company

    async def delete_company(self, company_id: int) -> bool:
        company = await self.get_company(company_id)
        if company is None:
            return False

        await self._session.execute(
            update(User)
            .where(User.company_id == company_id)
            .values(company_id=None)
        )
        await self._session.delete(company)
        await self._session.commit()
        return True

    async def activate_subscription(self, company_id: int, days: int = 30) -> Company:
        company = await self.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError("Kompaniya topilmadi.")

        now = self._utcnow()
        current_end = normalize_utc_datetime(company.subscription_end)
        base_date = current_end if current_end and current_end > now else now
        company.subscription_end = base_date + timedelta(days=days)
        company.is_active = True

        await self._session.commit()
        await self._session.refresh(company)
        company.subscription_end = normalize_utc_datetime(company.subscription_end)
        return company

    async def deactivate_subscription(self, company_id: int) -> Company:
        company = await self.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError("Kompaniya topilmadi.")

        company.subscription_end = None
        company.is_active = False

        await self._session.commit()
        await self._session.refresh(company)
        return company

    async def has_access(self, company_id: int) -> bool:
        company = await self.get_company(company_id)
        return bool(company and self.check_access(company))

    async def _find_by_name(self, name: str) -> Company | None:
        statement = select(Company).where(func.lower(Company.name) == name.lower())
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def _sync_subscription_state(self, companies: list[Company]) -> None:
        changed = False

        for company in companies:
            subscription_end = normalize_utc_datetime(company.subscription_end)
            if company.subscription_end != subscription_end:
                company.subscription_end = subscription_end
                changed = True

            has_access = self.check_access(company)
            if company.is_active != has_access:
                company.is_active = has_access
                changed = True

        if changed:
            await self._session.commit()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
