from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class AuthToken:
    """Entidad de dominio que representa un token de autenticación devuelto por el proveedor."""
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
    """Entidad que representa una clave pública JWK para verificación de firmas RSA."""
    kid: str
    kty: str
    alg: str
    use: str
    n: str
    e: str
    raw_data: Dict[str, Any]
