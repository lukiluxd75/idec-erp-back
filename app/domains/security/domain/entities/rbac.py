from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PermissionEntity:
    """Domain permission: an action on a concrete resource."""

    permission_id: Optional[str]
    action: str
    resource: Optional[str] = None
    description: Optional[str] = None

    @property
    def code(self) -> str:
        """Return 'resource.action' (see CLAUDE.md §8). Domain/system level is not
        assumed to map 1:1 to ERP domains until confirmed with the team."""
        return f"{self.resource}.{self.action}" if self.resource else self.action


@dataclass
class RoleEntity:
    """Internal role (table rol_interno). Independent from Keycloak roles."""

    role_id: Optional[str]
    name: str
    description: Optional[str] = None
    is_active: bool = True
    permissions: List[PermissionEntity] = field(default_factory=list)


@dataclass
class UserEntity:
    """Local user (table usuario) linked to Keycloak via keycloak_sub."""

    user_id: Optional[str]
    username: str
    keycloak_sub: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = True
    roles: List[RoleEntity] = field(default_factory=list)


@dataclass
class AreaEntity:
    """Organizational area (table area) — scope for user_role_area assignments."""

    area_id: Optional[str]
    name: str
    area_type: Optional[str] = None


@dataclass
class UserAssignmentEntity:
    """User plus current role(s) + area assignment (usuario_rol_area).
    Multiple roles under one active area are represented as N rows with the same area_id."""

    user_id: str
    username: str
    email: Optional[str]
    roles: List[RoleEntity] = field(default_factory=list)
    area_id: Optional[str] = None
    area_name: Optional[str] = None
    is_active: bool = True
