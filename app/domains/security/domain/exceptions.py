from app.core.errors.exceptions import DomainException

from app.core.security.exceptions import (  # noqa: F401
    InvalidCredentialsException,
    TokenVerificationException,
    TokenExpiredException,
    AuthProviderUnavailableException,
)


class InvalidDomainException(DomainException):
    """Raised when an institutional domain is invalid or empty."""
    pass


class InactiveUserException(DomainException):
    """Raised when a user marked inactive (usuario.is_active = false, see
    PermisosPage) tries to authenticate. The account still exists in Keycloak — the
    block is an ERP authorization decision, not Keycloak's (CLAUDE.md §5)."""
    http_status = 403


class RoleInUseException(DomainException):
    """Raised when deleting an internal role that still has users assigned
    (user_role_areas). Deleting it would violate the role_id FK; caught before
    the DB round-trip so the user gets a clear message instead of a raw 500."""
    http_status = 409


__all__ = [
    "DomainException",
    "InvalidDomainException",
    "InactiveUserException",
    "RoleInUseException",
    "InvalidCredentialsException",
    "TokenVerificationException",
    "TokenExpiredException",
    "AuthProviderUnavailableException",
]
