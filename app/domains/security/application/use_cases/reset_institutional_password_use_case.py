from app.domains.security.domain.ports.directory_provider_port import DirectoryProviderPort
from app.core.security.exceptions import InvalidCredentialsException
from app.domains.security.application.dtos.auth_dto import ResetInstitutionalPasswordInputDTO


class ResetInstitutionalPasswordUseCase:
    """
    Use case: administrative password reset for an institutional user
    directly in the Zentyal directory. Not self-service (does not require the
    user's current password) — uses the ZentyalLdapAdapter service account.
    """

    def __init__(self, directory_provider: DirectoryProviderPort):
        self._directory_provider = directory_provider

    def execute(self, input_dto: ResetInstitutionalPasswordInputDTO) -> None:
        username = (input_dto.username or "").strip()
        new_password = input_dto.new_password or ""

        if not username:
            raise InvalidCredentialsException("El nombre de usuario es requerido.")

        if len(new_password) < 8:
            raise InvalidCredentialsException("La nueva contraseña debe tener al menos 8 caracteres.")

        self._directory_provider.reset_password(username=username, new_password=new_password)
