from typing import Optional, List
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Schema for the login request."""
    domain: Optional[str] = Field(None, description="Institutional domain (e.g. gamc.gob.bo)")
    username: Optional[str] = Field(None, description="Username for direct access")
    password: Optional[str] = Field(None, description="User password")


class LoginResponse(BaseModel):
    """Schema for a successful login response."""
    message: str
    access_token: str
    domain: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


class RefreshRequest(BaseModel):
    """Schema for the session renewal request."""
    refresh_token: str = Field(..., description="Valid refresh token issued by Keycloak")


class ChangePasswordRequest(BaseModel):
    """Schema for the authenticated user password-change request."""
    current_password: str = Field(..., description="Current user password")
    new_password: str = Field(..., min_length=8, description="New password (minimum 8 characters)")


class ResetInstitutionalPasswordRequest(BaseModel):
    """Schema for admin password reset of an institutional user (Zentyal)."""
    username: str = Field(..., description="Institutional username (cn in the Zentyal directory)")
    new_password: str = Field(..., min_length=8, description="New password (minimum 8 characters)")


class PublicMessageResponse(BaseModel):
    """Response schema for public routes."""
    message: str


class DatabaseHealthResponse(BaseModel):
    """Response schema for PostgreSQL health check.

    `database` queda opcional a propósito: el endpoint que usa este esquema no
    pide autenticación, así que no publica el nombre de la base ni el detalle
    del error. Se conserva el campo (en None) para no romper sondas externas
    que ya parseen este JSON.
    """
    status: str
    database: Optional[str] = None
    message: str


class PrivateProfileResponse(BaseModel):
    """Response schema for protected profile information."""
    message: str
    usuario: str
    email: str
    roles: List[str] = []
    client_id: Optional[str] = None
    user_id: Optional[str] = None
    permisos: List[str] = []


class PhonePresenceOut(BaseModel):
    """Si la cuenta tiene un celular conectado ahora mismo. Mismo nombre de
    campo que devuelven los endpoints equivalentes de geoextraction,
    resolutions y folder analysis, para que el frontend los lea igual."""

    mobile_connected: bool
