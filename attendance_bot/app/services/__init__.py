from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.user_repo import UserRepository
from app.services.auth_service import AuthFlowResult, AuthService
from app.services.localization_service import LocalizationService
from app.services.super_admin_service import SuperAdminService


def build_localization_service() -> LocalizationService:
    return LocalizationService()


def build_super_admin_service(session: AsyncSession) -> SuperAdminService:
    return SuperAdminService(
        user_repo=UserRepository(session),
        localization_service=build_localization_service(),
    )


def build_auth_service(session: AsyncSession, settings: Settings) -> AuthService:
    user_repo = UserRepository(session)
    localization_service = build_localization_service()
    super_admin_service = SuperAdminService(
        user_repo=user_repo,
        localization_service=localization_service,
    )
    return AuthService(
        user_repo=user_repo,
        super_admin_service=super_admin_service,
        localization_service=localization_service,
        settings=settings,
    )


__all__ = (
    "AuthFlowResult",
    "AuthService",
    "LocalizationService",
    "SuperAdminService",
    "build_auth_service",
    "build_localization_service",
    "build_super_admin_service",
)
