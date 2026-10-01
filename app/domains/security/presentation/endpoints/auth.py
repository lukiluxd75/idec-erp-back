from fastapi import APIRouter, Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
import logging

from app.domains.security.presentation.schemas.auth_schema import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    ChangePasswordRequest,
    ResetInstitutionalPasswordRequest,
    PublicMessageResponse,
)
from app.domains.security.application.use_cases import (
    AuthenticateDomainUseCase,
    AuthenticateCredentialsUseCase,
    RefreshTokenUseCase,
    VerifyTokenUseCase,
    SyncUserRbacUseCase,
    ChangePasswordUseCase,
    ResetInstitutionalPasswordUseCase,
)
from app.domains.security.application.dtos.auth_dto import (
    DomainLoginInputDTO,
    CredentialsLoginInputDTO,
    RefreshTokenInputDTO,
    ChangePasswordInputDTO,
    ResetInstitutionalPasswordInputDTO,
)
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.security.presentation.endpoints.presence import record_session_from_request
from app.domains.security.domain.exceptions import InvalidDomainException, InactiveUserException
from app.domains.security.domain.entities.user import UserProfile
from app.domains.security.presentation.deps import (
    get_authenticate_domain_use_case,
    get_authenticate_credentials_use_case,
    get_refresh_token_use_case,
    get_verify_token_use_case,
    get_sync_user_rbac_use_case,
    get_change_password_use_case,
    get_reset_institutional_password_use_case,
    require_permission,
    security,
)

logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["Autenticación"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    domain_use_case: AuthenticateDomainUseCase = Depends(get_authenticate_domain_use_case),
    credentials_use_case: AuthenticateCredentialsUseCase = Depends(get_authenticate_credentials_use_case),
    verify_use_case: VerifyTokenUseCase = Depends(get_verify_token_use_case),
    sync_rbac: SyncUserRbacUseCase = Depends(get_sync_user_rbac_use_case),
):
    """
    Authentication endpoint supporting Institutional Domain and Direct Credentials.
    - If `domain` is sent: validate the institutional domain with Keycloak.
    - If `username` and `password` are sent: validate direct credentials against Keycloak
      and ensure the user exists in the 'usuario' table (without assigning roles).
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

        # Ensure the user exists in 'usuario' (linked by keycloak_sub).
        # InactiveUserException is allowed to propagate on purpose: if the user is
        # marked inactive, login must fail here — do not return a valid token and
        # fail only on the next screen.
        try:
            profile = verify_use_case.execute(result.access_token)
            sync_rbac.execute(
                keycloak_sub=profile.sub,
                username=profile.username,
                email=profile.email,
            )
            # "Celular conectado" sin tocar la app movil: si este login no viene
            # de un navegador de escritorio, queda registrada una sesion de
            # celular (ver endpoints/presence.py). La app ya llama a /login, asi
            # que el indicador se enciende solo al iniciar sesion.
            record_session_from_request(request, db, profile.sub)
        except InactiveUserException:
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
    request: Request,
    db: Session = Depends(get_db),
    refresh_use_case: RefreshTokenUseCase = Depends(get_refresh_token_use_case),
    verify_use_case: VerifyTokenUseCase = Depends(get_verify_token_use_case),
):
    """
    Renew the session from a valid refresh_token without requiring credentials.
    Allows a silent refresh from the frontend before the access_token expires.
    """
    result = refresh_use_case.execute(RefreshTokenInputDTO(refresh_token=payload.refresh_token))

    # El refresh es el latido natural de la app: lo llama sola cada vez que el
    # access_token esta por vencer, asi que renovar aqui la sesion mantiene el
    # indicador encendido mientras la app siga viva, sin pedirle nada nuevo.
    try:
        profile = verify_use_case.execute(result.access_token)
        record_session_from_request(request, db, profile.sub)
    except Exception as exc:
        logger.warning(f"Aviso al renovar la presencia del celular: {exc}")

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
    Change the authenticated user's password (Bearer token) against Keycloak.
    Requires the current password: Keycloak validates it via its Account REST API.
    """
    change_password_use_case.execute(
        ChangePasswordInputDTO(
            access_token=credentials.credentials,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    )
    return PublicMessageResponse(message="Contraseña actualizada correctamente.")


@router.post("/change-password-institutional", response_model=PublicMessageResponse)
def reset_institutional_password(
    payload: ResetInstitutionalPasswordRequest,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    use_case: ResetInstitutionalPasswordUseCase = Depends(get_reset_institutional_password_use_case),
):
    """
    Reset an institutional user's password directly in the Zentyal directory
    (LDAPS + unicodePwd), using the administrative service account configured
    by environment. Not self-service: does not validate the current password.

    Gated on `security.edit` — the same permission every other write in the
    security module requires (see endpoints/rbac_admin.py). That matters more here
    than anywhere else: the bind account this runs under can rewrite any
    `unicodePwd` in the directory, so a plain `get_current_user` would have let any
    authenticated user take over any institutional account.
    """
    use_case.execute(
        ResetInstitutionalPasswordInputDTO(
            username=payload.username,
            new_password=payload.new_password,
        )
    )
    return PublicMessageResponse(message="Contraseña institucional actualizada correctamente en el directorio.")
