from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


class RoleOut(BaseModel):
    """Internal role with permissions resolved as 'resource.action' codes.
    Spanish JSON keys kept for frontend compatibility."""

    id: str
    nombre: str
    descripcion: Optional[str] = None
    activo: bool = True
    permisos: List[str] = Field(default_factory=list)


class RoleCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=50)
    permisos: List[str] = Field(default_factory=list)


class RolePermissionsUpdateRequest(BaseModel):
    permisos: List[str] = Field(default_factory=list)


class AreaOut(BaseModel):
    id: str
    nombre: str
    tipo: Optional[str] = None


class AreaCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)


class AreaUpdateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)


class RoleSummaryOut(BaseModel):
    """Role assigned to a user, without permissions (edited on RolesPage)."""

    id: str
    nombre: str


class UserAssignmentOut(BaseModel):
    id: str
    username: str
    correo: Optional[str] = None
    roles: List[RoleSummaryOut] = Field(default_factory=list)
    area_id: Optional[str] = None
    area_nombre: Optional[str] = None
    activo: bool = True


class AssignRoleAreaRequest(BaseModel):
    """role_ids and area_id are sent together or both empty (CLAUDE.md §6).
    Accepts legacy 'rol_ids' for older clients."""

    model_config = ConfigDict(populate_by_name=True)

    role_ids: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("role_ids", "rol_ids"),
    )
    area_id: Optional[str] = None


class UserStatusUpdateRequest(BaseModel):
    """Activate/deactivate a user instead of deleting (CLAUDE.md §6)."""

    activo: bool
