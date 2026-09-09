from dataclasses import dataclass
from typing import Optional, List


@dataclass(frozen=True)
class DomainLoginInputDTO:
    """DTO de entrada para autenticación por dominio institucional."""
    domain: str


@dataclass(frozen=True)
class CredentialsLoginInputDTO:
    """DTO de entrada para autenticación por credenciales de usuario."""
    username: str
    password: str


@dataclass(frozen=True)
class RefreshTokenInputDTO:
    """DTO de entrada para renovación de sesión mediante refresh_token."""
    refresh_token: str


@dataclass(frozen=True)
class ChangePasswordInputDTO:
    """DTO de entrada para cambio de contraseña del usuario autenticado."""
    access_token: str
    current_password: str
    new_password: str


@dataclass(frozen=True)
class ResetInstitutionalPasswordInputDTO:
    """DTO de entrada para el reseteo administrativo de contraseña de un usuario institucional (Zentyal)."""
    username: str
    new_password: str


@dataclass(frozen=True)
class TokenOutputDTO:
    """DTO de salida tras un inicio de sesión exitoso."""
    message: str
    access_token: str
    domain: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


@dataclass(frozen=True)
class UserProfileOutputDTO:
    """DTO de salida para consulta de información del usuario autenticado."""
    message: str
    usuario: str
    email: str
    roles: List[str]
    client_id: Optional[str]
