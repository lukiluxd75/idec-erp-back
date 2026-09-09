from typing import List, Optional
from pydantic import BaseModel, Field


class RolOut(BaseModel):
    """Rol interno con sus permisos ya resueltos como códigos 'recurso.accion'
    (ej. 'geoextraccion.ver') — el mismo formato que usa el checklist de permisos
    del frontend (RolPermisosCheckboxes)."""
    id: str
    nombre: str
    descripcion: Optional[str] = None
    activo: bool = True
    permisos: List[str] = Field(default_factory=list)


class RolCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=50)
    permisos: List[str] = Field(default_factory=list)


class RolPermisosUpdateRequest(BaseModel):
    permisos: List[str] = Field(default_factory=list)


class AreaOut(BaseModel):
    id: str
    nombre: str
    tipo: Optional[str] = None


class AreaCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)


class AreaUpdateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)


class RolResumenOut(BaseModel):
    """Rol asignado a un usuario, sin sus permisos (esos se editan en RolesPage)."""
    id: str
    nombre: str


class UsuarioAsignacionOut(BaseModel):
    id: str
    username: str
    correo: Optional[str] = None
    roles: List[RolResumenOut] = Field(default_factory=list)
    area_id: Optional[str] = None
    area_nombre: Optional[str] = None
    activo: bool = True


class AsignarRolAreaRequest(BaseModel):
    """rol_ids y area_id se envían juntos o ambos vacíos: la base no admite un rol sin
    área ni viceversa (CLAUDE.md §6). rol_ids puede tener más de un rol — todos quedan
    bajo la misma área."""
    rol_ids: List[str] = Field(default_factory=list)
    area_id: Optional[str] = None


class UsuarioEstadoUpdateRequest(BaseModel):
    """Activar/desactivar un usuario (usuario.activo) en vez de borrarlo — ver CLAUDE.md §6."""
    activo: bool
