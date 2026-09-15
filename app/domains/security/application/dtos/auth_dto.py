from dataclasses import dataclass
from typing import Optional, List


@dataclass(frozen=True)
class DomainLoginInputDTO:
    """Input DTO for institutional domain authentication."""
    domain: str


@dataclass(frozen=True)
class CredentialsLoginInputDTO:
    """Input DTO for username/password authentication."""
    username: str
    password: str


@dataclass(frozen=True)
class RefreshTokenInputDTO:
    """Input DTO for session renewal via refresh_token."""
    refresh_token: str


@dataclass(frozen=True)
class ChangePasswordInputDTO:
    """Input DTO for password change by the authenticated user."""
    access_token: str
    current_password: str
    new_password: str


@dataclass(frozen=True)
class ResetInstitutionalPasswordInputDTO:
    """Input DTO for admin password reset of an institutional user (Zentyal)."""
    username: str
    new_password: str


@dataclass(frozen=True)
class TokenOutputDTO:
    """Output DTO after a successful login."""
    message: str
    access_token: str
    domain: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


@dataclass(frozen=True)
class UserProfileOutputDTO:
    """Output DTO for authenticated user profile information."""
    message: str
    usuario: str
    email: str
    roles: List[str]
    client_id: Optional[str]
