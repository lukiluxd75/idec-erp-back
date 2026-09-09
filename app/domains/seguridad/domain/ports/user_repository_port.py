from abc import ABC, abstractmethod
from typing import List, Optional

from app.domains.seguridad.domain.entities.rbac import UserEntity


class UserRepositoryPort(ABC):
    """
    Puerto (interfaz abstracta) para operaciones de persistencia del usuario y consulta
    RBAC contra el esquema real de PostgreSQL (tablas usuario, rol_interno,
    usuario_rol_area, permiso, rol_permiso).
    """

    @abstractmethod
    def get_by_keycloak_sub(self, keycloak_sub: str) -> Optional[UserEntity]:
        """Obtiene un usuario por su identificador de Keycloak (usuario.keycloak_sub)."""
        pass

    @abstractmethod
    def ensure_user_exists(
        self, keycloak_sub: str, username: str, correo: Optional[str] = None
    ) -> UserEntity:
        """
        Garantiza que exista un registro en 'usuario' para este keycloak_sub. Si el
        usuario es nuevo, además lo asigna a un punto de partida fijo — área "Catastro" +
        rol "Inicio" (ver SqlUserRepository) — para que no quede sin ningún permiso hasta
        que un admin se lo cambie a mano desde PermisosPage. Un usuario ya existente
        conserva la asignación que tenga, esto no la pisa.
        """
        pass

    @abstractmethod
    def get_user_permissions(self, keycloak_sub: str) -> List[str]:
        """
        Códigos de permiso ('recurso.accion') que el usuario tiene a través de los roles
        que le fueron asignados (en alguna área) en usuario_rol_area.
        """
        pass
