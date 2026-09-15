from functools import lru_cache
from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.domains.security.domain.ports.auth_provider_port import AuthProviderPort
from app.domains.security.domain.ports.user_repository_port import UserRepositoryPort
from app.domains.security.domain.ports.rbac_admin_repository_port import RbacAdminRepositoryPort
from app.domains.security.domain.ports.directory_provider_port import DirectoryProviderPort
from app.domains.security.domain.entities.user import UserProfile
from app.domains.security.application.use_cases import (
    AuthenticateDomainUseCase,
    AuthenticateCredentialsUseCase,
    RefreshTokenUseCase,
    VerifyTokenUseCase,
    SyncUserRbacUseCase,
    ChangePasswordUseCase,
    ResetInstitutionalPasswordUseCase,
    ListRolesUseCase,
    CreateRoleUseCase,
    SetRolePermissionsUseCase,
    DeleteRoleUseCase,
    ListAreasUseCase,
    CreateAreaUseCase,
    UpdateAreaUseCase,
    DeleteAreaUseCase,
    ListUserAssignmentsUseCase,
    AssignRoleAreaUseCase,
    SetUserActiveUseCase,
)
from app.domains.security.infrastructure.keycloak_adapter import KeycloakAdapter
from app.domains.security.infrastructure.zentyal_ldap_adapter import ZentyalLdapAdapter
from app.core.security.jwks_service import JWKSService
from app.core.database.connection import get_db
from app.domains.security.infrastructure.sql_user_repository import SqlUserRepository
from app.domains.security.infrastructure.sql_rbac_admin_repository import SqlRbacAdminRepository

# Bearer header extraction mechanism
security = HTTPBearer()


@lru_cache()
def get_jwks_service() -> JWKSService:
    """Cached singleton instance of the JWKS service."""
    return JWKSService()


@lru_cache()
def get_auth_provider() -> AuthProviderPort:
    """Cached singleton instance of the Keycloak adapter."""
    return KeycloakAdapter(jwks_service=get_jwks_service())


def get_authenticate_domain_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> AuthenticateDomainUseCase:
    """Dependency injector for the domain authentication use case."""
    return AuthenticateDomainUseCase(auth_provider=auth_provider)


def get_authenticate_credentials_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> AuthenticateCredentialsUseCase:
    """Dependency injector for the direct-credentials authentication use case."""
    return AuthenticateCredentialsUseCase(auth_provider=auth_provider)


def get_refresh_token_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> RefreshTokenUseCase:
    """Dependency injector for the session renewal use case."""
    return RefreshTokenUseCase(auth_provider=auth_provider)


def get_verify_token_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> VerifyTokenUseCase:
    """Dependency injector for the token verification use case."""
    return VerifyTokenUseCase(auth_provider=auth_provider)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepositoryPort:
    """Dependency injector for the PostgreSQL-backed user repository."""
    return SqlUserRepository(db=db)


def get_sync_user_rbac_use_case(
    user_repository: UserRepositoryPort = Depends(get_user_repository),
) -> SyncUserRbacUseCase:
    """Dependency injector for the RBAC sync use case."""
    return SyncUserRbacUseCase(user_repository=user_repository)


def get_change_password_use_case(
    auth_provider: AuthProviderPort = Depends(get_auth_provider),
) -> ChangePasswordUseCase:
    """Dependency injector for the password-change use case."""
    return ChangePasswordUseCase(auth_provider=auth_provider)


@lru_cache()
def get_directory_provider() -> DirectoryProviderPort:
    """Cached singleton instance of the Zentyal directory adapter."""
    return ZentyalLdapAdapter()


def get_reset_institutional_password_use_case(
    directory_provider: DirectoryProviderPort = Depends(get_directory_provider),
) -> ResetInstitutionalPasswordUseCase:
    """Dependency injector for the institutional admin password-reset use case."""
    return ResetInstitutionalPasswordUseCase(directory_provider=directory_provider)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    verify_use_case: VerifyTokenUseCase = Depends(get_verify_token_use_case),
    user_repository: UserRepositoryPort = Depends(get_user_repository),
) -> UserProfile:
    """
    FastAPI dependency to protect endpoints.
    Extracts the Bearer token, validates it against Keycloak, and returns the UserProfile entity.

    Also rejects here a user marked inactive (usuario.is_active = false, see
    PermisosPage): since every protected endpoint uses this dependency, this single
    check is enough so a mid-session deactivation cuts access on the next request,
    not only on the next /login. If the token 'sub' still has no row in 'usuario'
    (never logged in with credentials), allow through — nothing to block yet.
    """
    token = credentials.credentials
    profile = verify_use_case.execute(token)

    if profile.sub:
        usuario = user_repository.get_by_keycloak_sub(profile.sub)
        if usuario and not usuario.is_active:
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
    Internal id (table 'usuario') of the authenticated user, or None if they still
    have no row (e.g. never logged in with credentials, which is the only path that
    currently triggers SyncUserRbacUseCase — see presentation/endpoints/auth.py).
    Used to record who performed an administrative write (CLAUDE.md §9).
    """
    entity = user_repository.get_by_keycloak_sub(current_user.sub) if current_user.sub else None
    return entity.user_id if entity else None


# --- RBAC administration (roles, areas, user-role-area assignment) --------------------


def get_rbac_admin_repository(db: Session = Depends(get_db)) -> RbacAdminRepositoryPort:
    return SqlRbacAdminRepository(db=db)


def get_list_roles_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> ListRolesUseCase:
    return ListRolesUseCase(repository=repo)


def get_create_role_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> CreateRoleUseCase:
    return CreateRoleUseCase(repository=repo)


def get_set_role_permissions_use_case(
    repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository),
) -> SetRolePermissionsUseCase:
    return SetRolePermissionsUseCase(repository=repo)


def get_delete_role_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> DeleteRoleUseCase:
    return DeleteRoleUseCase(repository=repo)


def get_list_areas_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> ListAreasUseCase:
    return ListAreasUseCase(repository=repo)


def get_create_area_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> CreateAreaUseCase:
    return CreateAreaUseCase(repository=repo)


def get_update_area_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> UpdateAreaUseCase:
    return UpdateAreaUseCase(repository=repo)


def get_delete_area_use_case(repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository)) -> DeleteAreaUseCase:
    return DeleteAreaUseCase(repository=repo)


def get_list_user_assignments_use_case(
    repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository),
) -> ListUserAssignmentsUseCase:
    return ListUserAssignmentsUseCase(repository=repo)


def get_assign_role_area_use_case(
    repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository),
) -> AssignRoleAreaUseCase:
    return AssignRoleAreaUseCase(repository=repo)


def get_set_user_active_use_case(
    repo: RbacAdminRepositoryPort = Depends(get_rbac_admin_repository),
) -> SetUserActiveUseCase:
    return SetUserActiveUseCase(repository=repo)


def require_permission(codigo: str):
    """
    FastAPI dependency factory: requires the authenticated user to hold permission
    'codigo' (format 'resource.action', e.g. 'geoextraction.edit') among those
    granted by roles assigned in usuario_rol_area. Usage: `Depends(require_permission("x.y"))`.

    This is the first time the backend resolves a real authorization decision from
    the internal RBAC model instead of the Keycloak role (CLAUDE.md §5). Also exposed
    from contracts/ (see contracts/authorization.py) so other domains can protect
    themselves with the same mechanism without importing security internal layers —
    CLAUDE.md §2.
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
