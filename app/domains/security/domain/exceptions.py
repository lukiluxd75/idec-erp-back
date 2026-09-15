from app.core.errors.exceptions import DomainException

# Technical auth/token exceptions (Keycloak communication) live in
# core.security.exceptions, because any domain integrating Keycloak needs them,
# not only `security`. Re-exported here for convenience within this domain.
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


__all__ = [
    "DomainException",
    "InvalidDomainException",
    "InactiveUserException",
    "InvalidCredentialsException",
    "TokenVerificationException",
    "TokenExpiredException",
    "AuthProviderUnavailableException",
]
