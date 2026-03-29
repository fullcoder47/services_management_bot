from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.db.models.user import User
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
    requires_language_selection: bool = False
    is_authorized: bool = False
    user: UserDTO | None = None
    follow_up_message: str | None = None


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

        if user is None or user.language is None:
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

        return await self._finalize_access(
            user=user,
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            language=user.language,
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

        return await self._finalize_access(
            user=user,
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            language=language,
            selected_language_now=True,
        )

    async def _finalize_access(
        self,
        *,
        user: User | None,
        telegram_id: int,
        full_name: str,
        username: str | None,
        language: Language,
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
                    follow_up_message=self.super_admin_service.panel_message(language, super_admin.full_name),
                )
            return AuthFlowResult(
                message=self.super_admin_service.panel_message(language, super_admin.full_name),
                language=language,
                is_authorized=True,
                user=super_admin,
            )

        known_user = await self._ensure_denied_user(
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

    async def _ensure_denied_user(
        self,
        *,
        user: User | None,
        telegram_id: int,
        full_name: str,
        username: str | None,
        language: Language,
    ) -> UserDTO:
        if user is None:
            user = await self.user_repo.create(
                telegram_id=telegram_id,
                full_name=full_name,
                username=username,
                phone=None,
                role=Role.EMPLOYEE,
                language=language,
                is_active=False,
            )
            return UserDTO.from_model(user)

        if user.language != language:
            await self.user_repo.update_language(user, language)

        return UserDTO.from_model(user)
