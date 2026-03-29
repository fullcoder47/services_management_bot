from __future__ import annotations

import logging

from app.db.repositories.user_repo import UserRepository
from app.domain.dto.user_dto import UserDTO
from app.domain.enums.language import Language
from app.domain.enums.role import Role
from app.domain.exceptions.auth_exceptions import AccessDeniedError
from app.services.localization_service import LocalizationService


logger = logging.getLogger(__name__)


class SuperAdminService:
    def __init__(
        self,
        *,
        user_repo: UserRepository,
        localization_service: LocalizationService,
    ) -> None:
        self.user_repo = user_repo
        self.localization_service = localization_service

    async def ensure_super_admin(
        self,
        *,
        telegram_id: int,
        full_name: str,
        username: str | None,
        language: Language,
    ) -> UserDTO:
        user = await self.user_repo.get_by_telegram_id(telegram_id)

        if user is None:
            user = await self.user_repo.create(
                telegram_id=telegram_id,
                full_name=full_name,
                username=username,
                role=Role.SUPER_ADMIN,
                language=language,
                is_active=True,
            )
            return UserDTO.from_model(user)

        await self.user_repo.update_last_known_fields(
            user,
            full_name=full_name,
            username=username,
        )

        if user.role is not Role.SUPER_ADMIN:
            logger.warning(
                "Promoting user %s from role %s to super_admin based on settings",
                telegram_id,
                user.role.value,
            )
            await self.user_repo.update_role(user, Role.SUPER_ADMIN)

        if user.language != language:
            await self.user_repo.update_language(user, language)

        if not user.is_active:
            await self.user_repo.update_active_state(user, is_active=True)

        return UserDTO.from_model(user)

    def require_super_admin(self, current_user: UserDTO | None) -> UserDTO:
        if current_user is None or not current_user.is_active or current_user.role is not Role.SUPER_ADMIN:
            raise AccessDeniedError
        return current_user

    def panel_message(self, *, language: Language, full_name: str) -> str:
        return self.localization_service.super_admin_panel(language=language, full_name=full_name)

    def companies_placeholder(self, language: Language) -> str:
        return self.localization_service.companies_placeholder(language)

    def statistics_placeholder(self, language: Language) -> str:
        return self.localization_service.statistics_placeholder(language)

    def settings_placeholder(self, language: Language) -> str:
        return self.localization_service.settings_placeholder(language)

    def access_denied_message(self, language: Language | None) -> str:
        return self.localization_service.access_denied(language)
