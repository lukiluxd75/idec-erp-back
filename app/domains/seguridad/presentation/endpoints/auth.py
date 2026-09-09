from fastapi import APIRouter, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials
import logging

from app.domains.seguridad.presentation.schemas.auth_schema import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    ChangePasswordRequest,
    ResetInstitutionalPasswordRequest,
    PublicMessageResponse,
)
from app.domains.seguridad.application.use_cases import (
    AuthenticateDomainUseCase,
    AuthenticateCredentialsUseCase,
    RefreshTokenUseCase,
    VerifyTokenUseCase,
    SyncUserRbacUseCase,
    ChangePasswordUseCase,
    ResetInstitutionalPasswordUseCase,
)
from app.domains.seguridad.application.dtos.auth_dto import (
    DomainLoginInputDTO,
    CredentialsLoginInputDTO,
    RefreshTokenInputDTO,
    ChangePasswordInputDTO,
    ResetInstitutionalPasswordInputDTO,
)
from app.domains.seguridad.domain.exceptions import InvalidDomainException, UsuarioInactivoException
from app.domains.seguridad.domain.entities.user import UserProfile
from app.domains.seguridad.presentation.deps import (
    get_authenticate_domain_use_case,
    get_authenticate_credentials_use_case,
    get_refresh_token_use_case,
    get_verify_token_use_case,
    get_sync_user_rbac_use_case,
    get_change_password_use_case,
    get_reset_institutional_password_use_case,
    get_current_user,
    security,
)

logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["Autenticación"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    domain_use_case: AuthenticateDomainUseCase = Depends(get_authenticate_domain_use_case),
    credentials_use_case: AuthenticateCredentialsUseCase = Depends(get_authenticate_credentials_use_case),
    verify_use_case: VerifyTokenUseCase = Depends(get_verify_token_use_case),
    sync_rbac: SyncUserRbacUseCase = Depends(get_sync_user_rbac_use_case),
):
    """
    Endpoint de Autenticación compatible con Dominio Institucional y Credenciales Directas.
    - Si se envía `domain`: Valida el dominio institucional con Keycloak.
    - Si se envía `username` y `password`: Valida credenciales directas contra Keycloak
      y garantiza que el usuario exista en la tabla 'usuario' (sin asignar roles).
    """
    if payload.domain:
        result = domain_use_case.execute(DomainLoginInputDTO(domain=payload.domain))
        return LoginResponse(
            message=result.message,
            access_token=result.access_token,
            domain=result.domain,
        )

    if payload.username and payload.password:
        result = credentials_use_case.execute(
            CredentialsLoginInputDTO(
                username=payload.username,
                password=payload.password,
            )
        )

        # Garantizar que el usuario exista en 'usuario' (vinculado por keycloak_sub).
        # UsuarioInactivoException se deja propagar a propósito: si el usuario está
        # marcado como inactivo, el login debe rechazarse acá, no devolver un token
        # válido y fallar recién en la siguiente pantalla (ver PermisosPage).
        try:
            profile = verify_use_case.execute(result.access_token)
            sync_rbac.execute(
                keycloak_sub=profile.sub,
                username=profile.username,
                correo=profile.email,
            )
        except UsuarioInactivoException:
            raise
        except Exception as exc:
            logger.warning(f"Aviso al guardar usuario en base de datos: {exc}")

        return LoginResponse(
            message=result.message,
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            expires_in=result.expires_in,
        )

    raise InvalidDomainException("Debe ingresar un dominio institucional o usuario y contraseña.")


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    payload: RefreshRequest,
    refresh_use_case: RefreshTokenUseCase = Depends(get_refresh_token_use_case),
):
    """
    Renueva la sesión a partir de un refresh_token vigente, sin requerir credenciales.
    Permite un refresh silencioso desde el frontend antes de que expire el access_token.
    """
    result = refresh_use_case.execute(RefreshTokenInputDTO(refresh_token=payload.refresh_token))

    return LoginResponse(
        message=result.message,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
    )


@router.post("/change-password", response_model=PublicMessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Security(security),
    change_password_use_case: ChangePasswordUseCase = Depends(get_change_password_use_case),
):
    """
    Cambia la contraseña del usuario autenticado (Bearer token) contra Keycloak.
    Requiere la contraseña actual: Keycloak la valida vía su Account REST API.
    """
    change_password_use_case.execute(
        ChangePasswordInputDTO(
            access_token=credentials.credentials,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    )
    return PublicMessageResponse(message="Contraseña actualizada correctamente.")


@router.post("/change-password-institucional", response_model=PublicMessageResponse)
def reset_institutional_password(
    payload: ResetInstitutionalPasswordRequest,
    current_user: UserProfile = Depends(get_current_user),
    use_case: ResetInstitutionalPasswordUseCase = Depends(get_reset_institutional_password_use_case),
):
    """
    Resetea la contraseña de un usuario institucional directamente en el directorio
    Zentyal (LDAPS + unicodePwd), usando la cuenta de servicio administrativa
    configurada por entorno. No es self-service: no valida la contraseña actual.

    ⚠️ Solo exige un Bearer token válido (`get_current_user`). Todavía NO valida un
    permiso de negocio fino (ej. `seguridad.usuarios.resetear_password_institucional`)
    porque ese mecanismo de autorización por permisos no está implementado en el
    backend aún (CLAUDE.md §4/§10). Hoy, cualquier usuario autenticado puede resetear
    la contraseña de cualquier otro usuario institucional — no exponer este endpoint
    fuera de un ambiente de pruebas sin resolver esto antes.
    """
    use_case.execute(
        ResetInstitutionalPasswordInputDTO(
            username=payload.username,
            new_password=payload.new_password,
        )
    )
    return PublicMessageResponse(message="Contraseña institucional actualizada correctamente en el directorio.")
