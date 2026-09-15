from app.domains.security.domain.ports.auth_provider_port import AuthProviderPort
from app.core.security.exceptions import InvalidCredentialsException
from app.domains.security.application.dtos.auth_dto import RefreshTokenInputDTO, TokenOutputDTO


class RefreshTokenUseCase:
    """
    Use case: silent session renewal from a valid refresh_token.
    """

    def __init__(self, auth_provider: AuthProviderPort):
        self._auth_provider = auth_provider

    def execute(self, input_dto: RefreshTokenInputDTO) -> TokenOutputDTO:
        refresh_token = input_dto.refresh_token or ""

        if not refresh_token:
            raise InvalidCredentialsException("El refresh_token es requerido.")

        token = self._auth_provider.refresh_token(refresh_token)

        return TokenOutputDTO(
            message="Sesión renovada",
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_in=token.expires_in,
        )
