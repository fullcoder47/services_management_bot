from __future__ import annotations


class AuthError(Exception):
    """Base authentication exception."""


class AccessDeniedError(AuthError):
    """Raised when a user cannot access a protected area."""


class LanguageSelectionRequiredError(AuthError):
    """Raised when a language must be selected before continuing."""
