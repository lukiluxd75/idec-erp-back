from app.domains.seguridad.domain.ports.auth_provider_port import AuthProviderPort
from app.core.security.exceptions import InvalidCredentialsException
from app.domains.seguridad.application.dtos.auth_dto import CredentialsLoginInputDTO, TokenOutputDTO


class AuthenticateCredentialsUseCase:
    """
    Caso de uso: Autenticación por usuario y contraseña (Direct Access Grant).
    """

    def __init__(self, auth_provider: AuthProviderPort):
        self._auth_provider = auth_provider

    def execute(self, input_dto: CredentialsLoginInputDTO) -> TokenOutputDTO:
        username = (input_dto.username or "").strip()
        password = input_dto.password or ""

        if not username or not password:
            raise InvalidCredentialsException("El nombre de usuario y la contraseña son requeridos.")

        token = self._auth_provider.authenticate_credentials(username, password)

        return TokenOutputDTO(
            message="Credenciales correctas",
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_in=token.expires_in,
        )
