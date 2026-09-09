from app.domains.seguridad.domain.ports.auth_provider_port import AuthProviderPort
from app.domains.seguridad.domain.exceptions import InvalidDomainException
from app.domains.seguridad.application.dtos.auth_dto import DomainLoginInputDTO, TokenOutputDTO


class AuthenticateDomainUseCase:
    """
    Caso de uso: Autenticación institucional por nombre de dominio.
    Valida el formato del dominio y orquesta la obtención del token mediante el AuthProviderPort.
    """

    def __init__(self, auth_provider: AuthProviderPort):
        self._auth_provider = auth_provider

    def execute(self, input_dto: DomainLoginInputDTO) -> TokenOutputDTO:
        clean_domain = (input_dto.domain or "").strip().lower()

        if not clean_domain:
            raise InvalidDomainException("El dominio no puede estar vacío.")

        token = self._auth_provider.authenticate_domain(clean_domain)

        return TokenOutputDTO(
            message=f"Dominio '{clean_domain}' validado con Keycloak",
            access_token=token.access_token,
            domain=clean_domain,
        )
