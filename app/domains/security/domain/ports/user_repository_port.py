from abc import ABC, abstractmethod
from typing import List, Optional

from app.domains.security.domain.entities.rbac import UserEntity


class UserRepositoryPort(ABC):
    """
    Port (abstract interface) for user persistence and RBAC queries against the
    real PostgreSQL schema (tables usuario, rol_interno, usuario_rol_area,
    permiso, rol_permiso).
    """

    @abstractmethod
    def get_by_keycloak_sub(self, keycloak_sub: str) -> Optional[UserEntity]:
        """Get a user by their Keycloak identifier (usuario.keycloak_sub)."""
        pass

    @abstractmethod
    def ensure_user_exists(
        self, keycloak_sub: str, username: str, email: Optional[str] = None
    ) -> UserEntity:
        """
        Ensure a 'usuario' row exists for this keycloak_sub. If the user is new,
        also assign a fixed starting point — area "Catastro" + role "Inicio"
        (see SqlUserRepository) — so they are not left without any permission
        until an admin changes it by hand from PermisosPage. An existing user
        keeps whatever assignment they already have; this does not overwrite it.
        """
        pass

    @abstractmethod
    def get_user_permissions(self, keycloak_sub: str) -> List[str]:
        """
        Permission codes ('resource.action') the user has through roles assigned
        to them (in some area) in usuario_rol_area.
        """
        pass
