from typing import Optional, List
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Esquema para la solicitud de inicio de sesión."""
    domain: Optional[str] = Field(None, description="Dominio institucional (ej. gamc.gob.bo)")
    username: Optional[str] = Field(None, description="Nombre de usuario para acceso directo")
    password: Optional[str] = Field(None, description="Contraseña de usuario")


class LoginResponse(BaseModel):
    """Esquema de respuesta exitosa de inicio de sesión."""
    message: str
    access_token: str
    domain: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


class RefreshRequest(BaseModel):
    """Esquema para la solicitud de renovación de sesión."""
    refresh_token: str = Field(..., description="Refresh token vigente emitido por Keycloak")


class ChangePasswordRequest(BaseModel):
    """Esquema para la solicitud de cambio de contraseña del usuario autenticado."""
    current_password: str = Field(..., description="Contraseña actual del usuario")
    new_password: str = Field(..., min_length=8, description="Nueva contraseña (mínimo 8 caracteres)")


class ResetInstitutionalPasswordRequest(BaseModel):
    """Esquema para el reseteo administrativo de contraseña de un usuario institucional (Zentyal)."""
    username: str = Field(..., description="Nombre de usuario institucional (cn en el directorio Zentyal)")
    new_password: str = Field(..., min_length=8, description="Nueva contraseña (mínimo 8 caracteres)")


class PublicMessageResponse(BaseModel):
    """Esquema de respuesta para rutas públicas."""
    message: str


class DatabaseHealthResponse(BaseModel):
    """Esquema de respuesta para verificación del estado de PostgreSQL."""
    status: str
    database: str
    message: str


class PrivateProfileResponse(BaseModel):
    """Esquema de respuesta para información de perfil protegido."""
    message: str
    usuario: str
    email: str
    roles: List[str] = []
    client_id: Optional[str] = None
    id_usuario: Optional[str] = None
    permisos: List[str] = []
