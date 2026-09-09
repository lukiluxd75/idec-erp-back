from typing import List, Optional

from app.domains.seguridad.domain.entities.rbac import AreaEntity, RoleEntity, UsuarioAsignacionEntity
from app.domains.seguridad.domain.ports.rbac_admin_repository_port import RbacAdminRepositoryPort

"""
Casos de uso de la pantalla de administración de roles/áreas/asignaciones que
CLAUDE.md §10 marca como pendiente. Cada uno es una acción de negocio concreta, delgada
sobre RbacAdminRepositoryPort — sin lógica propia más allá de delegar (la lógica de
resolución del catálogo permiso/recurso vive en el adaptador, ver
infrastructure/sql_rbac_admin_repository.py).
"""


class ListRolesUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self) -> List[RoleEntity]:
        return self._repository.list_roles()


class CreateRolUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, nombre: str) -> RoleEntity:
        return self._repository.create_role(nombre)


class SetRolPermisosUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, rol_id: str, codigos: List[str], actor_usuario_id: Optional[str]) -> RoleEntity:
        return self._repository.set_role_permissions(rol_id, codigos, actor_usuario_id)


class DeleteRolUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, rol_id: str, actor_usuario_id: Optional[str]) -> None:
        self._repository.delete_role(rol_id, actor_usuario_id)


class ListAreasUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self) -> List[AreaEntity]:
        return self._repository.list_areas()


class CreateAreaUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, nombre: str) -> AreaEntity:
        return self._repository.create_area(nombre)


class UpdateAreaUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, area_id: str, nombre: str) -> AreaEntity:
        return self._repository.update_area(area_id, nombre)


class DeleteAreaUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, area_id: str, actor_usuario_id: Optional[str]) -> None:
        self._repository.delete_area(area_id, actor_usuario_id)


class ListUsuariosAsignacionUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self) -> List[UsuarioAsignacionEntity]:
        return self._repository.list_usuarios_con_asignacion()


class AsignarRolAreaUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(
        self,
        usuario_id: str,
        rol_ids: List[str],
        area_id: Optional[str],
        actor_usuario_id: Optional[str],
    ) -> UsuarioAsignacionEntity:
        return self._repository.asignar_rol_area(usuario_id, rol_ids, area_id, actor_usuario_id)


class SetUsuarioActivoUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(
        self, usuario_id: str, activo: bool, actor_usuario_id: Optional[str]
    ) -> UsuarioAsignacionEntity:
        return self._repository.set_usuario_activo(usuario_id, activo, actor_usuario_id)
