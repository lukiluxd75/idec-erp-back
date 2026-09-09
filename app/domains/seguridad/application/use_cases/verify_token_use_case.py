from app.domains.seguridad.domain.ports.auth_provider_port import AuthProviderPort
from app.domains.seguridad.domain.entities.user import UserProfile
from app.core.security.exceptions import TokenVerificationException


class VerifyTokenUseCase:
    """
    Caso de uso: Verificación criptográfica de token y extracción del perfil del usuario.
    """

    def __init__(self, auth_provider: AuthProviderPort):
        self._auth_provider = auth_provider

    def execute(self, raw_token: str) -> UserProfile:
        if not raw_token:
            raise TokenVerificationException("No se proporcionó ningún token")

        return self._auth_provider.verify_token(raw_token)
