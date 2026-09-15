from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class AuthToken:
    """Domain entity representing an authentication token returned by the provider."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    refresh_expires_in: Optional[int] = None
    scope: Optional[str] = None
    domain: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class JWKKey:
    """Entity representing a public JWK for RSA signature verification."""
    kid: str
    kty: str
    alg: str
    use: str
    n: str
    e: str
    raw_data: Dict[str, Any]
