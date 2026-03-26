from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Request, RequestStatus, User, UserRole


class RequestServiceError(Exception):
    pass


class RequestNotFoundError(RequestServiceError):
    pass


class RequestAccessDeniedError(RequestServiceError):
    pass


class RequestValidationError(RequestServiceError):
    pass


class RequestStateError(RequestServiceError):
    pass


@dataclass(slots=True)
class CreateRequestDTO:
    user_id: int
    company_id: int
    phone: str
    problem_text: str


@dataclass(slots=True)
class CompleteRequestDTO:
    result_text: str
    result_image: str


class RequestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_request(self, payload: CreateRequestDTO) -> Request:
        phone = payload.phone.strip()
        problem_text = payload.problem_text.strip()

        if not phone:
            raise RequestValidationError("Telefon raqami majburiy.")
        if not problem_text:
            raise RequestValidationError("Muammo tavsifi majburiy.")

        request = Request(
            user_id=payload.user_id,
            company_id=payload.company_id,
            phone=phone,
            problem_text=problem_text,
            status=RequestStatus.PENDING,
            result_text=None,
            result_image="",
            completed_at=None,
        )
        self._session.add(request)
        await self._session.commit()
        await self._session.refresh(request)
        return await self.get_request_or_raise(request.id)

    async def get_request(self, request_id: int) -> Request | None:
        statement = (
            select(Request)
            .options(
                selectinload(Request.user),
                selectinload(Request.company),
            )
            .where(Request.id == request_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_request_or_raise(self, request_id: int) -> Request:
        request = await self.get_request(request_id)
        if request is None:
            raise RequestNotFoundError("Ariza topilmadi.")
        return request

    async def list_requests_for_manager(self, actor: User) -> list[Request]:
        self.ensure_can_manage_requests(actor)
        if actor.company_id is None:
            return []

        statement = (
            select(Request)
            .options(
                selectinload(Request.user),
                selectinload(Request.company),
            )
            .where(Request.company_id == actor.company_id)
            .order_by(Request.created_at.desc(), Request.id.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_user_requests(self, user_id: int) -> list[Request]:
        statement = (
            select(Request)
            .options(selectinload(Request.company))
            .where(Request.user_id == user_id)
            .order_by(Request.created_at.desc(), Request.id.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_management_recipients(self, company_id: int) -> list[User]:
        statement = (
            select(User)
            .where(
                User.company_id == company_id,
                User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]),
            )
            .order_by(User.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_in_progress(self, request_id: int, actor: User) -> Request:
        request = await self.get_request_or_raise(request_id)
        self.ensure_management_access(actor, request)

        if request.status == RequestStatus.DONE:
            raise RequestStateError("Bajarilgan arizani qayta qabul qilib bo'lmaydi.")

        if request.status != RequestStatus.IN_PROGRESS:
            request.status = RequestStatus.IN_PROGRESS
            await self._session.commit()
            await self._session.refresh(request)

        return await self.get_request_or_raise(request.id)

    async def complete_request(
        self,
        request_id: int,
        actor: User,
        payload: CompleteRequestDTO,
    ) -> Request:
        request = await self.get_request_or_raise(request_id)
        self.ensure_management_access(actor, request)

        result_text = payload.result_text.strip()
        result_image = payload.result_image.strip()

        if not result_text:
            raise RequestValidationError("Bajarilgan ish tavsifi majburiy.")
        if not result_image:
            raise RequestValidationError("Bajarilgan ish rasmi majburiy.")
        if request.status == RequestStatus.DONE:
            raise RequestStateError("Bu ariza allaqachon bajarilgan.")

        request.status = RequestStatus.DONE
        request.result_text = result_text
        request.result_image = result_image
        request.completed_at = self._utcnow()

        await self._session.commit()
        await self._session.refresh(request)
        return await self.get_request_or_raise(request.id)

    def ensure_can_manage_requests(self, actor: User) -> None:
        if actor.role not in {UserRole.ADMIN, UserRole.OPERATOR}:
            raise RequestAccessDeniedError("Bu bo'lim faqat admin va operator uchun.")

    def ensure_management_access(self, actor: User, request: Request) -> None:
        self.ensure_can_manage_requests(actor)
        if actor.company_id is None or request.company_id != actor.company_id:
            raise RequestAccessDeniedError("Siz bu arizani boshqara olmaysiz.")

    @staticmethod
    def format_status(status: RequestStatus) -> str:
        if status == RequestStatus.PENDING:
            return "🆕 Kutilmoqda"
        if status == RequestStatus.IN_PROGRESS:
            return "🛠 Jarayonda"
        return "✅ Bajarildi"

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
