"""
Punto de entrada público del dominio `seguridad` para el resto de dominios del ERP.
Cualquier otro dominio que necesite saber "quién es el usuario autenticado" importa
desde aquí — nunca desde `domains.seguridad.presentation.deps` ni de sus capas internas
(ver CLAUDE.md §2: "Dominio A -> contracts/ de Dominio B" es el único punto permitido).
"""
from app.domains.seguridad.domain.entities.user import UserProfile
from app.domains.seguridad.presentation.deps import get_auth_provider, get_current_user
from app.domains.seguridad.application.use_cases import VerifyTokenUseCase


def verify_token(raw_token: str) -> UserProfile:
    """
    Variante de `get_current_user` para transportes que no pueden mandar un header
    `Authorization` (ej. el WebSocket del dominio `resoluciones`, que recibe el token
    por query string — el WebSocket API del navegador no permite headers custom).
    Valida el token igual que `get_current_user`, solo que a partir de un string crudo
    en vez de la dependencia `Security(HTTPBearer())` de FastAPI.
    """
    return VerifyTokenUseCase(auth_provider=get_auth_provider()).execute(raw_token)


__all__ = ["UserProfile", "get_current_user", "verify_token"]
