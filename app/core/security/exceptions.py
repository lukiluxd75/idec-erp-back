from app.core.errors.exceptions import DomainException


class InvalidCredentialsException(DomainException):
    """Raised when the provided credentials (username/password or client credentials) are incorrect."""
    http_status = 401
    headers = {"WWW-Authenticate": "Bearer"}


class TokenVerificationException(DomainException):
    """Raised when a JWT cannot be verified or has an invalid signature/claims."""
    http_status = 401
    headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'}


class TokenExpiredException(TokenVerificationException):
    """Raised when a JWT has expired."""
    headers = {
        "WWW-Authenticate": 'Bearer error="invalid_token", error_description="The token has expired"'
    }


class AuthProviderUnavailableException(DomainException):
    """Raised when the authentication server (Keycloak) is unreachable or the connection fails."""
    http_status = 502


class DirectoryProviderUnavailableException(DomainException):
    """Raised when the institutional directory (Zentyal/LDAP) is unreachable, not configured, or bind fails."""
    http_status = 502
