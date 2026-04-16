from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Company, CompanyChatChannel, CompanyChatMessage, User, UserRole
from services.company_service import CompanyService


class ChatServiceError(Exception):
    pass


class ChatAccessDeniedError(ChatServiceError):
    pass


class ChatValidationError(ChatServiceError):
    pass


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_companies_for_actor(self, actor: User) -> list[Company]:
        if actor.is_super_admin:
            return await CompanyService(self._session).list_companies()
        if actor.company_id is None:
            return []
        company = await CompanyService(self._session).get_company(actor.company_id)
        return [company] if company is not None else []

    async def list_company_chat_messages(
        self,
        actor: User,
        company_id: int,
        channel_type: CompanyChatChannel,
        *,
        limit: int = 20,
    ) -> tuple[Company, list[CompanyChatMessage]]:
        company = await self._get_company_or_raise(company_id)
        self.ensure_channel_access(actor, company_id, channel_type)

        statement = (
            select(CompanyChatMessage)
            .options(selectinload(CompanyChatMessage.sender))
            .where(
                CompanyChatMessage.company_id == company_id,
                CompanyChatMessage.channel_type == channel_type,
            )
            .order_by(CompanyChatMessage.created_at.desc(), CompanyChatMessage.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        messages = list(reversed(result.scalars().all()))
        return company, messages

    async def create_company_chat_message(
        self,
        actor: User,
        company_id: int,
        channel_type: CompanyChatChannel,
        text: str,
    ) -> CompanyChatMessage:
        self.ensure_channel_access(actor, company_id, channel_type)
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ChatValidationError("Chat uchun xabar matni majburiy.")

        message = CompanyChatMessage(
            company_id=company_id,
            channel_type=channel_type,
            sender_user_id=actor.id,
            sender_role=actor.role,
            text=cleaned_text,
            created_at=self._utcnow(),
        )
        self._session.add(message)
        await self._session.commit()
        await self._session.refresh(message)
        return await self.get_company_chat_message_or_raise(message.id)

    async def get_company_chat_message(self, message_id: int) -> CompanyChatMessage | None:
        statement = (
            select(CompanyChatMessage)
            .options(
                selectinload(CompanyChatMessage.sender),
                selectinload(CompanyChatMessage.company),
            )
            .where(CompanyChatMessage.id == message_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_company_chat_message_or_raise(self, message_id: int) -> CompanyChatMessage:
        message = await self.get_company_chat_message(message_id)
        if message is None:
            raise ChatValidationError("Chat xabari topilmadi.")
        return message

    async def get_general_chat_recipients(
        self,
        company_id: int,
        channel_type: CompanyChatChannel,
        sender: User,
    ) -> tuple[Company, list[User]]:
        company = await self._get_company_or_raise(company_id)
        self.ensure_channel_access(sender, company_id, channel_type)

        roles = (
            [UserRole.USER, UserRole.ADMIN, UserRole.SUPER_ADMIN]
            if channel_type == CompanyChatChannel.COMPANY_USERS
            else [UserRole.ADMIN, UserRole.SUPER_ADMIN]
        )
        statement = (
            select(User)
            .where(
                User.role.in_(roles),
                (
                    (User.company_id == company_id)
                    | (User.role == UserRole.SUPER_ADMIN)
                ),
            )
            .order_by(User.id.asc())
        )
        result = await self._session.execute(statement)
        users = [user for user in result.scalars().all() if user.id != sender.id]
        return company, users

    def ensure_channel_access(
        self,
        actor: User,
        company_id: int,
        channel_type: CompanyChatChannel,
    ) -> None:
        if actor.role == UserRole.USER:
            if actor.company_id != company_id or channel_type != CompanyChatChannel.COMPANY_USERS:
                raise ChatAccessDeniedError("Siz bu chatga kira olmaysiz.")
            return

        if actor.role == UserRole.ADMIN:
            if actor.company_id != company_id:
                raise ChatAccessDeniedError("Admin faqat o'z kompaniyasi chatiga kira oladi.")
            if channel_type not in {
                CompanyChatChannel.COMPANY_USERS,
                CompanyChatChannel.COMPANY_ADMINS,
            }:
                raise ChatAccessDeniedError("Admin uchun chat kanali noto'g'ri.")
            return

        if actor.role == UserRole.SUPER_ADMIN:
            return

        raise ChatAccessDeniedError("Bu chat bo'limi sizga mavjud emas.")

    async def _get_company_or_raise(self, company_id: int) -> Company:
        company = await CompanyService(self._session).get_company(company_id)
        if company is None:
            raise ChatValidationError("Kompaniya topilmadi.")
        return company

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
