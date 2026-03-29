from __future__ import annotations


class AuthError(Exception):
    """Base authentication exception."""


class AccessDeniedError(AuthError):
    """Raised when a user cannot access the bot."""


class SuperAdminRoleConflictError(AuthError):
    """Raised when a super admin bootstrap detects an inconsistent user role."""
