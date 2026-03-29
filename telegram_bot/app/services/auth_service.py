from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.db.repositories.user_repo import UserRepository
from app.domain.dto.user_dto import UserDTO
from app.domain.enums.language import Language
from app.domain.enums.role import Role
from app.services.localization_service import LocalizationService
from app.services.super_admin_service import SuperAdminService


@dataclass(slots=True)
class AuthFlowResult:
    message: str
    language: Language | None
    is_authorized: bool = False
    requires_language_selection: bool = False
    user: UserDTO | None = None
    panel_message: str | None = None


class AuthService:
    def __init__(
        self,
        *,
        user_repo: UserRepository,
        super_admin_service: SuperAdminService,
        localization_service: LocalizationService,
        settings: Settings,
    ) -> None:
        self.user_repo = user_repo
        self.super_admin_service = super_admin_service
        self.localization_service = localization_service
        self.settings = settings

    async def process_start(
        self,
        *,
        telegram_id: int,
        full_name: str,
        username: str | None,
    ) -> AuthFlowResult:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return AuthFlowResult(
                message=self.localization_service.select_language_prompt(),
                language=None,
                requires_language_selection=True,
            )

        await self.user_repo.update_last_known_fields(
            user,
            full_name=full_name,
            username=username,
        )

        if user.language is None:
            return AuthFlowResult(
                message=self.localization_service.select_language_prompt(),
                language=None,
                requires_language_selection=True,
            )

        return await self._continue_after_language(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            language=user.language,
            user=user,
            selected_language_now=False,
        )

    async def process_language_selection(
        self,
        *,
        telegram_id: int,
        full_name: str,
        username: str | None,
        language: Language,
    ) -> AuthFlowResult:
        user = await self.user_repo.get_by_telegram_id(telegram_id)

        if user is not None:
            await self.user_repo.update_last_known_fields(
                user,
                full_name=full_name,
                username=username,
            )
            await self.user_repo.update_language(user, language)

        return await self._continue_after_language(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            language=language,
            user=user,
            selected_language_now=True,
        )

    async def _continue_after_language(
        self,
        *,
        telegram_id: int,
        full_name: str,
        username: str | None,
        language: Language,
        user: Any,
        selected_language_now: bool,
    ) -> AuthFlowResult:
        if self.settings.is_super_admin(telegram_id):
            super_admin = await self.super_admin_service.ensure_super_admin(
                telegram_id=telegram_id,
                full_name=full_name,
                username=username,
                language=language,
            )
            if selected_language_now:
                return AuthFlowResult(
                    message=self.localization_service.language_saved(language),
                    language=language,
                    is_authorized=True,
                    user=super_admin,
                    panel_message=self.super_admin_service.panel_message(
                        language=language,
                        full_name=super_admin.full_name,
                    ),
                )
            return AuthFlowResult(
                message=self.super_admin_service.panel_message(
                    language=language,
                    full_name=super_admin.full_name,
                ),
                language=language,
                is_authorized=True,
                user=super_admin,
            )

        known_user = await self._ensure_known_user(
            user=user,
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            language=language,
        )
        denied_message = self.localization_service.access_denied(language)
        if selected_language_now:
            denied_message = self.localization_service.language_saved_and_denied(language)
        return AuthFlowResult(
            message=denied_message,
            language=language,
            is_authorized=False,
            user=known_user,
        )

    async def _ensure_known_user(
        self,
        *,
        user: Any,
        telegram_id: int,
        full_name: str,
        username: str | None,
        language: Language,
    ) -> UserDTO:
        if user is None:
            created_user = await self.user_repo.create(
                telegram_id=telegram_id,
                full_name=full_name,
                username=username,
                role=Role.EMPLOYEE,
                language=language,
                is_active=False,
            )
            return UserDTO.from_model(created_user)

        if user.language != language:
            await self.user_repo.update_language(user, language)

        return UserDTO.from_model(user)
