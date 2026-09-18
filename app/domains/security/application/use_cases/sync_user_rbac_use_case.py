from typing import List, Optional, Tuple

from app.domains.security.domain.entities.rbac import UserEntity
from app.domains.security.domain.exceptions import InactiveUserException
from app.domains.security.domain.ports.user_repository_port import UserRepositoryPort


INSTITUTIONAL_SUB_SENTINEL = "institucional"


class SyncUserRbacUseCase:
    """
    Use case: ensure the Keycloak-authenticated user has a PostgreSQL row
    (linked by keycloak_sub) and retrieve permissions already assigned in the
    internal RBAC model.

    Does not assign roles from Keycloak roles: CLAUDE.md §5 is explicit that
    business authorization decisions must never be taken from the Keycloak role
    directly. What it does (delegated to SqlUserRepository.ensure_user_exists)
    is give every new user a fixed starting point — area "Catastro" + role
    "Inicio", not chosen from anything in Keycloak — instead of leaving them
    with no permissions until an admin assigns them by hand from PermisosPage.

    "Institutional" case: when the token has no 'sub' (e.g. a client_credentials
    token, or a Keycloak account that does not represent a person — such as the
    admin-cli/realm master credentials used for testing today), there is no real
    individual identity to link. Instead of discarding the sync attempt, the
    same 'Institucional' user is always reused (via INSTITUTIONAL_SUB_SENTINEL),
    as the previous backend version did. NOTE: this means no action under these
    conditions can be audited per person — confirm with the team whether this is
    acceptable long-term or whether a real Keycloak user per person is needed
    (see CLAUDE.md §10).
    """

    def __init__(self, user_repository: UserRepositoryPort):
        self._user_repository = user_repository

    def execute(
        self, keycloak_sub: str, username: str, email: Optional[str] = None
    ) -> Tuple[UserEntity, List[str]]:
        clean_sub = (keycloak_sub or "").strip()
        clean_username = (username or "").strip() or "usuario_anonimo"

        if not clean_sub:
            clean_sub = INSTITUTIONAL_SUB_SENTINEL
            clean_username = clean_username if clean_username != "usuario_anonimo" else "Institucional"

        existing_user = self._user_repository.get_by_keycloak_sub(clean_sub)
        if existing_user and not existing_user.is_active:
            raise InactiveUserException(
                "Su usuario está inactivo. Contacte a un administrador."
            )

        user_entity = self._user_repository.ensure_user_exists(
            keycloak_sub=clean_sub, username=clean_username, email=email
        )
        permissions = self._user_repository.get_user_permissions(clean_sub)
        return user_entity, permissions
