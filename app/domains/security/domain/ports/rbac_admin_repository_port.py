from abc import ABC, abstractmethod
from typing import List, Optional

from app.domains.security.domain.entities.rbac import (
    AreaEntity,
    RoleEntity,
    UserAssignmentEntity,
)


class RbacAdminRepositoryPort(ABC):
    """
    Port for the roles/areas/user-role-area admin screen (rol_interno, area,
    usuario_rol_area, permiso, rol_permiso) — the piece CLAUDE.md §10 marks as
    pending ("today there is none; it is done manually in the database").
    """

    @abstractmethod
    def list_roles(self) -> List[RoleEntity]:
        """Active internal roles, with permissions resolved as 'resource.action' codes."""
        pass

    @abstractmethod
    def create_role(self, name: str) -> RoleEntity:
        """Create a new internal role, with no permissions yet."""
        pass

    @abstractmethod
    def set_role_permissions(self, role_id: str, codes: List[str], actor_user_id: Optional[str]) -> RoleEntity:
        """
        Fully replace a role's permission set. Each 'resource.action' code is
        resolved to a real row in 'permiso' (creating it if needed, along with
        its 'recurso' — never a permission checked only in code without a table
        row, CLAUDE.md §4).
        """
        pass

    @abstractmethod
    def delete_role(self, role_id: str, actor_user_id: Optional[str]) -> None:
        """Delete an internal role. That role's usuario_rol_area rows go with it
        (ON DELETE CASCADE on the real database)."""
        pass

    @abstractmethod
    def list_areas(self) -> List[AreaEntity]:
        pass

    @abstractmethod
    def create_area(self, name: str) -> AreaEntity:
        pass

    @abstractmethod
    def update_area(self, area_id: str, name: str) -> AreaEntity:
        pass

    @abstractmethod
    def delete_area(self, area_id: str, actor_user_id: Optional[str]) -> None:
        pass

    @abstractmethod
    def list_users_with_assignment(self) -> List[UserAssignmentEntity]:
        """All users (table 'usuario') with their current role+area, if any.
        Includes both active and inactive — an admin needs to see inactive users
        to reactivate them, not only deactivate them (see set_user_active)."""
        pass

    @abstractmethod
    def assign_role_area(
        self,
        user_id: str,
        role_ids: List[str],
        area_id: Optional[str],
        actor_user_id: Optional[str],
    ) -> UserAssignmentEntity:
        """
        Replace a user's assignment with the one given: one usuario_rol_area row
        per role_id in role_ids, all with the same area_id (several roles may
        coexist under one area). If role_ids is empty or area_id is missing, the
        user is left with no assignment (the DB requires both together or
        neither: there is no usuario_rol_area without area, CLAUDE.md §6).
        """
        pass

    @abstractmethod
    def set_user_active(
        self, user_id: str, is_active: bool, actor_user_id: Optional[str]
    ) -> UserAssignmentEntity:
        """
        Mark a user active/inactive (usuario.is_active) instead of deleting —
        the real table already has this column for that (CLAUDE.md §6). Does not
        touch their roles/area: a reactivated user keeps the assignment they
        already had. An inactive user cannot authenticate again (see
        SyncUserRbacUseCase / get_current_user).
        """
        pass
