from __future__ import annotations

from dataclasses import dataclass

from db.models import User, UserRole
from services.user_service import UserService


@dataclass(slots=True)
class HelpContext:
    description_key: str
    contacts: list[User]
    empty_key: str


class HelpService:
    def __init__(self, user_service: UserService) -> None:
        self._user_service = user_service

    async def get_help_context(self, actor: User) -> HelpContext:
        if actor.is_super_admin:
            return HelpContext(
                description_key="help_super_admin_text",
                contacts=[],
                empty_key="help_super_admin_empty",
            )

        if actor.role == UserRole.USER:
            contacts = await self._get_company_admins(actor.company_id)
            return HelpContext(
                description_key="help_user_text",
                contacts=contacts,
                empty_key="help_no_admin",
            )

        if actor.role in {UserRole.ADMIN, UserRole.OPERATOR}:
            contacts = await self._user_service.get_super_admins()
            return HelpContext(
                description_key="help_admin_text",
                contacts=[user for user in contacts if user.id != actor.id],
                empty_key="help_no_super_admin",
            )

        if actor.role == UserRole.WORKER:
            contacts = await self._get_company_admins(actor.company_id)
            if contacts:
                return HelpContext(
                    description_key="help_worker_text",
                    contacts=contacts,
                    empty_key="help_no_admin",
                )

            super_admins = await self._user_service.get_super_admins()
            return HelpContext(
                description_key="help_worker_super_admin_text",
                contacts=[user for user in super_admins if user.id != actor.id],
                empty_key="help_no_super_admin",
            )

        return HelpContext(
            description_key="help_user_text",
            contacts=[],
            empty_key="help_no_admin",
        )

    async def _get_company_admins(self, company_id: int | None) -> list[User]:
        if company_id is None:
            return []
        return await self._user_service.get_company_admins(company_id)
