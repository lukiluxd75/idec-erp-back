from typing import List, Optional

from app.domains.security.domain.entities.rbac import AreaEntity, RoleEntity, UserAssignmentEntity
from app.domains.security.domain.ports.rbac_admin_repository_port import RbacAdminRepositoryPort

"""
Use cases for the roles/areas/assignments admin screen that CLAUDE.md §10 marks
as pending. Each is a concrete business action, thin over
RbacAdminRepositoryPort — no logic beyond delegation (permission/resource
catalog resolution lives in the adapter, see
infrastructure/sql_rbac_admin_repository.py).
"""


class ListRolesUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self) -> List[RoleEntity]:
        return self._repository.list_roles()


class CreateRoleUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, name: str) -> RoleEntity:
        return self._repository.create_role(name)


class SetRolePermissionsUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, role_id: str, codes: List[str], actor_user_id: Optional[str]) -> RoleEntity:
        return self._repository.set_role_permissions(role_id, codes, actor_user_id)


class DeleteRoleUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, role_id: str, actor_user_id: Optional[str]) -> None:
        self._repository.delete_role(role_id, actor_user_id)


class ListAreasUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self) -> List[AreaEntity]:
        return self._repository.list_areas()


class CreateAreaUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, name: str) -> AreaEntity:
        return self._repository.create_area(name)


class UpdateAreaUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, area_id: str, name: str) -> AreaEntity:
        return self._repository.update_area(area_id, name)


class DeleteAreaUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self, area_id: str, actor_user_id: Optional[str]) -> None:
        self._repository.delete_area(area_id, actor_user_id)


class ListUserAssignmentsUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(self) -> List[UserAssignmentEntity]:
        return self._repository.list_users_with_assignment()


class AssignRoleAreaUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(
        self,
        user_id: str,
        role_ids: List[str],
        area_id: Optional[str],
        actor_user_id: Optional[str],
    ) -> UserAssignmentEntity:
        return self._repository.assign_role_area(user_id, role_ids, area_id, actor_user_id)


class SetUserActiveUseCase:
    def __init__(self, repository: RbacAdminRepositoryPort):
        self._repository = repository

    def execute(
        self, user_id: str, is_active: bool, actor_user_id: Optional[str]
    ) -> UserAssignmentEntity:
        return self._repository.set_user_active(user_id, is_active, actor_user_id)
