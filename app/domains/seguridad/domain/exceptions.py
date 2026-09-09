from app.core.errors.exceptions import DomainException

# Excepciones técnicas de autenticación/tokens (comunicación con Keycloak) viven en
# core.security.exceptions, porque cualquier dominio que integre Keycloak las necesita,
# no solo `seguridad`. Se re-exportan acá por comodidad para el código de este dominio.
from app.core.security.exceptions import (  # noqa: F401
    InvalidCredentialsException,
    TokenVerificationException,
    TokenExpiredException,
    AuthProviderUnavailableException,
)


class InvalidDomainException(DomainException):
    """Se lanza cuando un dominio institucional es inválido o está vacío."""
    pass


class UsuarioInactivoException(DomainException):
    """Se lanza cuando un usuario marcado como inactivo (usuario.activo = false, ver
    PermisosPage) intenta autenticarse. La cuenta sigue existiendo en Keycloak — el
    bloqueo es una decisión de autorización del ERP, no de Keycloak (CLAUDE.md §5)."""
    http_status = 403


__all__ = [
    "DomainException",
    "InvalidDomainException",
    "UsuarioInactivoException",
    "InvalidCredentialsException",
    "TokenVerificationException",
    "TokenExpiredException",
    "AuthProviderUnavailableException",
]
