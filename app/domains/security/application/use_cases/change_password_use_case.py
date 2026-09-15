from app.domains.security.domain.ports.auth_provider_port import AuthProviderPort
from app.core.security.exceptions import InvalidCredentialsException
from app.domains.security.application.dtos.auth_dto import ChangePasswordInputDTO


class ChangePasswordUseCase:
    """
    Use case: password change for the authenticated user (self-service against Keycloak).
    """

    def __init__(self, auth_provider: AuthProviderPort):
        self._auth_provider = auth_provider

    def execute(self, input_dto: ChangePasswordInputDTO) -> None:
        current_password = input_dto.current_password or ""
        new_password = input_dto.new_password or ""

        if not current_password or not new_password:
            raise InvalidCredentialsException("La contraseña actual y la nueva contraseña son requeridas.")

        if len(new_password) < 8:
            raise InvalidCredentialsException("La nueva contraseña debe tener al menos 8 caracteres.")

        self._auth_provider.change_password(
            access_token=input_dto.access_token,
            current_password=current_password,
            new_password=new_password,
        )
