from functools import lru_cache
from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.domains.seguridad.domain.ports.auth_provider_port import AuthProviderPort
from app.domains.seguridad.domain.ports.user_repository_port import UserRepositoryPort
from app.domains.seguridad.domain.ports.rbac_admin_repository_port import RbacAdminRepositoryPort
from app.domains.seguridad.domain.ports.directory_provider_port import DirectoryProviderPort
from app.domains.seguridad.domain.entities.user import UserProfile
from app.domains.seguridad.application.use_cases import (
    AuthenticateDomainUseCase,
    AuthenticateCredentialsUseCase,
    RefreshTokenUseCase,
    VerifyTokenUseCase,
    SyncUserRbacUseCase,
    ChangePasswordUseCase,
    ResetInstitutionalPasswordUseCase,
    ListRolesUseCase,
    CreateRolUseCase,
    SetRolPermisosUseCase,
    DeleteRolUseCase,
    ListAreasUseCase,
    CreateAreaUseCase,
    UpdateAreaUseCase,
    DeleteAreaUseCase,
    ListUsuariosAsignacionUseCase,
    AsignarRolAreaUseCase,
    SetUsuarioActivoUseCase,
)
from app.domains.seguridad.infrastructure.keycloak_adapter import KeycloakAdapter
from app.domains.seguridad.infrastructure.zentyal_ldap_adapter import ZentyalLdapAdapter
from app.core.security.jwks_service import JWKSService
from app.core.database.connection import get_db
from app.domains.seguridad.infrastructure.sql_user_repository import SqlUserRepository
from app.domains.seguridad.infrastructure.sql_rbac_admin_repository import SqlRbacAdminRepository

# Mecanismo de extracción de cabecera Bearer
security = HTTPBearer()


@lru_cache()
def get_jwks_service() -> JWKSService:
    """Instancia única (singleton cacheado) para el servicio JWKS."""
    return JWKSService()


@lru_cache()
def get_auth_provider() -> AuthProviderPort:
    """Instancia única (singleton cacheado) del adaptador de Keycloak."""
    return KeycloakAdapter(jwks_service=get_jwks_service())


def get_authenticate_domain_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> AuthenticateDomainUseCase:
    """Inyector del caso de uso de autenticación por dominio."""
    return AuthenticateDomainUseCase(auth_provider=auth_provider)


def get_authenticate_credentials_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> AuthenticateCredentialsUseCase:
    """Inyector del caso de uso de autenticación por credenciales directas."""
    return AuthenticateCredentialsUseCase(auth_provider=auth_provider)


def get_refresh_token_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> RefreshTokenUseCase:
    """Inyector del caso de uso de renovación de sesión."""
    return RefreshTokenUseCase(auth_provider=auth_provider)


def get_verify_token_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> VerifyTokenUseCase:
    """Inyector del caso de uso de verificación de tokens."""
    return VerifyTokenUseCase(auth_provider=auth_provider)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepositoryPort:
    """Inyector del repositorio de usuarios conectado a PostgreSQL."""
    return SqlUserRepository(db=db)


def get_sync_user_rbac_use_case(
    user_repository: UserRepositoryPort = Depends(get_user_repository),
) -> SyncUserRbacUseCase:
    """Inyector del caso de uso de sincronización RBAC."""
    return SyncUserRbacUseCase(user_repository=user_repository)


def get_change_password_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> ChangePasswordUseCase:
    """Inyector del caso de uso de cambio de contraseña."""
    return ChangePasswordUseCase(auth_provider=auth_provider)


@lru_cache()
def get_directory_provider() -> DirectoryProviderPort:
    """Instancia única (singleton cacheado) del adaptador de directorio Zentyal."""
    return ZentyalLdapAdapter()


def get_reset_institutional_password_use_case(
    directory_provider: DirectoryProviderPort = Depends(get_directory_provider),
) -> ResetInstitutionalPasswordUseCase:
    """Inyector del caso de uso de reseteo administrativo de contraseña institucional."""
    return ResetInstitutionalPasswordUseCase(directory_provider=directory_provider)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    verify_use_case: VerifyTokenUseCase = Depends(get_verify_token_use_case),
    user_repository: UserRepositoryPort = Depends(get_user_repository),
) -> UserProfile:
    """
    Dependencia de FastAPI para proteger endpoints.
    Extrae el token Bearer, lo valida contra Keycloak y retorna la entidad UserProfile.

    También rechaza acá a un usuario marcado como inactivo (usuario.activo = false, ver
    PermisosPage): como esta dependencia la usan todos los endpoints protegidos, alcanza
    con este único chequeo para que una desactivación a mitad de sesión corte el acceso
    en el siguiente request, no solo en el próximo /login. Si el 'sub' del token todavía
    no tiene fila en 'usuario' (nunca hizo login por credenciales), se deja pasar — no hay
    nada que bloquear todavía.
    """
    token = credentials.credentials
    profile = verify_use_case.execute(token)

    if profile.sub:
        usuario = user_repository.get_by_keycloak_sub(profile.sub)
        if usuario and not usuario.activo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu usuario está inactivo. Contactá a un administrador.",
            )

    return profile


def get_current_usuario_id(
    current_user: UserProfile = Depends(get_current_user),
    user_repository: UserRepositoryPort = Depends(get_user_repository),
) -> Optional[str]:
    """
    Id interno (tabla 'usuario') del usuario autenticado, o None si todavía no tiene
    fila propia (p. ej. nunca hizo login por credenciales, que es lo único que hoy
    dispara SyncUserRbacUseCase — ver presentation/endpoints/auth.py). Se usa para dejar
    constancia de quién hizo una escritura administrativa (CLAUDE.md §9).
    """
    entity = user_repository.get_by_keycloak_sub(current_user.sub) if current_user.sub else None
    return entity.id_usuario if entity else None


# --- Administración RBAC (roles, áreas, asignación usuario-rol-área) --------------------


def get_rbac_admin_repository(db: Session = Depends(get_db)) -> RbacAdminRepositoryPort:
    return SqlRbacAdminRepository(db=db)


def get_list_roles_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> ListRolesUseCase:
    return ListRolesUseCase(repository=repo)


def get_create_rol_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> CreateRolUseCase:
    return CreateRolUseCase(repository=repo)


def get_set_rol_permisos_use_case(
    repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository),
) -> SetRolPermisosUseCase:
    return SetRolPermisosUseCase(repository=repo)


def get_delete_rol_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> DeleteRolUseCase:
    return DeleteRolUseCase(repository=repo)


def get_list_areas_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> ListAreasUseCase:
    return ListAreasUseCase(repository=repo)


def get_create_area_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> CreateAreaUseCase:
    return CreateAreaUseCase(repository=repo)


def get_update_area_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> UpdateAreaUseCase:
    return UpdateAreaUseCase(repository=repo)


def get_delete_area_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> DeleteAreaUseCase:
    return DeleteAreaUseCase(repository=repo)


def get_list_usuarios_asignacion_use_case(
    repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository),
) -> ListUsuariosAsignacionUseCase:
    return ListUsuariosAsignacionUseCase(repository=repo)


def get_asignar_rol_area_use_case(
    repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository),
) -> AsignarRolAreaUseCase:
    return AsignarRolAreaUseCase(repository=repo)


def get_set_usuario_activo_use_case(
    repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository),
) -> SetUsuarioActivoUseCase:
    return SetUsuarioActivoUseCase(repository=repo)


def require_permission(codigo: str):
    """
    Fábrica de dependencia de FastAPI: exige que el usuario autenticado tenga el permiso
    'codigo' (formato 'recurso.accion', ej. 'geoextraccion.editar') entre los que le
    otorgan sus roles asignados en usuario_rol_area. Uso: `Depends(require_permission("x.y"))`.

    Esta es la primera vez que el backend resuelve una decisión de autorización real a
    partir del modelo RBAC interno en vez del rol de Keycloak (CLAUDE.md §5). Se expone
    también desde contracts/ (ver contracts/authorization.py) para que otros dominios
    puedan protegerse con el mismo mecanismo sin importar nada de las capas internas de
    seguridad — CLAUDE.md §2.
    """

    def _dependency(
        current_user: UserProfile = Depends(get_current_user),
        user_repository: UserRepositoryPort = Depends(get_user_repository),
    ) -> UserProfile:
        permisos = user_repository.get_user_permissions(current_user.sub) if current_user.sub else []
        if codigo not in permisos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tenés el permiso '{codigo}' para realizar esta acción.",
            )
        return current_user

    return _dependency
