from app.core.errors.exceptions import DomainException


class InvalidCredentialsException(DomainException):
    """Se lanza cuando las credenciales proporcionadas (usuario/contraseña o client credentials) son incorrectas."""
    http_status = 401
    headers = {"WWW-Authenticate": "Bearer"}


class TokenVerificationException(DomainException):
    """Se lanza cuando un token JWT no puede ser verificado o tiene firma/claims inválidos."""
    http_status = 401
    headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'}


class TokenExpiredException(TokenVerificationException):
    """Se lanza cuando un token JWT ha expirado."""
    headers = {
        "WWW-Authenticate": 'Bearer error="invalid_token", error_description="The token has expired"'
    }


class AuthProviderUnavailableException(DomainException):
    """Se lanza cuando el servidor de autenticación (Keycloak) es inalcanzable o falla la conexión."""
    http_status = 502


class DirectoryProviderUnavailableException(DomainException):
    """Se lanza cuando el directorio institucional (Zentyal/LDAP) es inalcanzable, no está configurado o falla el bind."""
    http_status = 502
