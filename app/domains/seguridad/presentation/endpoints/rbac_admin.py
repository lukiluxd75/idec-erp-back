from typing import Optional
from fastapi import APIRouter, Depends

from app.domains.seguridad.domain.entities.user import UserProfile
from app.domains.seguridad.application.use_cases import (
    ListRolesUseCase,
    CreateRolUseCase,
    SetRolPermisosUseCase,
    DeleteRolUseCase,
    ListAreasUseCase,
    CreateAreaUseCase,
    UpdateAreaUseCase,
    DeleteAreaUseCase,
    ListUsuariosAsignacionUseCase,
    AsignarRolAreaUseCase,
    SetUsuarioActivoUseCase,
)
from app.domains.seguridad.presentation.deps import (
    get_current_user,
    get_current_usuario_id,
    get_list_roles_use_case,
    get_create_rol_use_case,
    get_set_rol_permisos_use_case,
    get_delete_rol_use_case,
    get_list_areas_use_case,
    get_create_area_use_case,
    get_update_area_use_case,
    get_delete_area_use_case,
    get_list_usuarios_asignacion_use_case,
    get_asignar_rol_area_use_case,
    get_set_usuario_activo_use_case,
)
from app.domains.seguridad.presentation.schemas.rbac_admin_schema import (
    RolOut,
    RolCreateRequest,
    RolPermisosUpdateRequest,
    RolResumenOut,
    AreaOut,
    AreaCreateRequest,
    AreaUpdateRequest,
    UsuarioAsignacionOut,
    AsignarRolAreaRequest,
    UsuarioEstadoUpdateRequest,
)
from app.domains.seguridad.presentation.schemas.auth_schema import PublicMessageResponse

# ⚠️ Todos los endpoints de acá abajo solo exigen un Bearer token válido
# (get_current_user), igual que /change-password-institucional en auth.py. Ninguno
# valida todavía un permiso de negocio fino (ej. "seguridad.roles.administrar") porque
# hacerlo sería la gallina y el huevo: es justamente acá donde se otorgan los primeros
# permisos, y hoy nadie tiene ninguno asignado (CLAUDE.md §5, "sin roles por defecto").
# No exponer esta pantalla fuera de un ambiente controlado sin resolver antes con
# negocio/arquitectura cómo se bootstrapea el primer administrador (CLAUDE.md §10).
router = APIRouter(tags=["Seguridad — Roles y Permisos"])


def _rol_to_out(entity) -> RolOut:
    return RolOut(
        id=entity.id_rol,
        nombre=entity.nombre,
        descripcion=entity.descripcion,
        activo=entity.activo,
        permisos=[permiso.codigo for permiso in entity.permisos],
    )


def _area_to_out(entity) -> AreaOut:
    return AreaOut(id=entity.id_area, nombre=entity.nombre, tipo=entity.tipo)


def _usuario_to_out(entity) -> UsuarioAsignacionOut:
    return UsuarioAsignacionOut(
        id=entity.id_usuario,
        username=entity.username,
        correo=entity.correo,
        roles=[RolResumenOut(id=rol.id_rol, nombre=rol.nombre) for rol in entity.roles],
        area_id=entity.area_id,
        area_nombre=entity.area_nombre,
        activo=entity.activo,
    )


@router.get("/roles", response_model=list[RolOut])
def listar_roles(
    _current_user: UserProfile = Depends(get_current_user),
    use_case: ListRolesUseCase = Depends(get_list_roles_use_case),
):
    return [_rol_to_out(rol) for rol in use_case.execute()]


@router.post("/roles", response_model=RolOut)
def crear_rol(
    payload: RolCreateRequest,
    _current_user: UserProfile = Depends(get_current_user),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    create_use_case: CreateRolUseCase = Depends(get_create_rol_use_case),
    set_permisos_use_case: SetRolPermisosUseCase = Depends(get_set_rol_permisos_use_case),
):
    rol = create_use_case.execute(payload.nombre.strip())
    if payload.permisos:
        rol = set_permisos_use_case.execute(rol.id_rol, payload.permisos, actor_id)
    return _rol_to_out(rol)


@router.put("/roles/{rol_id}/permisos", response_model=RolOut)
def actualizar_permisos_rol(
    rol_id: str,
    payload: RolPermisosUpdateRequest,
    _current_user: UserProfile = Depends(get_current_user),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: SetRolPermisosUseCase = Depends(get_set_rol_permisos_use_case),
):
    rol = use_case.execute(rol_id, payload.permisos, actor_id)
    return _rol_to_out(rol)


@router.delete("/roles/{rol_id}", response_model=PublicMessageResponse)
def eliminar_rol(
    rol_id: str,
    _current_user: UserProfile = Depends(get_current_user),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: DeleteRolUseCase = Depends(get_delete_rol_use_case),
):
    use_case.execute(rol_id, actor_id)
    return PublicMessageResponse(message="Rol eliminado correctamente.")


@router.get("/areas", response_model=list[AreaOut])
def listar_areas(
    _current_user: UserProfile = Depends(get_current_user),
    use_case: ListAreasUseCase = Depends(get_list_areas_use_case),
):
    return [_area_to_out(area) for area in use_case.execute()]


@router.post("/areas", response_model=AreaOut)
def crear_area(
    payload: AreaCreateRequest,
    _current_user: UserProfile = Depends(get_current_user),
    use_case: CreateAreaUseCase = Depends(get_create_area_use_case),
):
    return _area_to_out(use_case.execute(payload.nombre.strip()))


@router.put("/areas/{area_id}", response_model=AreaOut)
def actualizar_area(
    area_id: str,
    payload: AreaUpdateRequest,
    _current_user: UserProfile = Depends(get_current_user),
    use_case: UpdateAreaUseCase = Depends(get_update_area_use_case),
):
    return _area_to_out(use_case.execute(area_id, payload.nombre.strip()))


@router.delete("/areas/{area_id}", response_model=PublicMessageResponse)
def eliminar_area(
    area_id: str,
    _current_user: UserProfile = Depends(get_current_user),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: DeleteAreaUseCase = Depends(get_delete_area_use_case),
):
    use_case.execute(area_id, actor_id)
    return PublicMessageResponse(message="Área eliminada correctamente.")


@router.get("/usuarios", response_model=list[UsuarioAsignacionOut])
def listar_usuarios(
    _current_user: UserProfile = Depends(get_current_user),
    use_case: ListUsuariosAsignacionUseCase = Depends(get_list_usuarios_asignacion_use_case),
):
    return [_usuario_to_out(usuario) for usuario in use_case.execute()]


@router.put("/usuarios/{usuario_id}/asignacion", response_model=UsuarioAsignacionOut)
def asignar_rol_area(
    usuario_id: str,
    payload: AsignarRolAreaRequest,
    _current_user: UserProfile = Depends(get_current_user),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: AsignarRolAreaUseCase = Depends(get_asignar_rol_area_use_case),
):
    resultado = use_case.execute(usuario_id, payload.rol_ids, payload.area_id, actor_id)
    return _usuario_to_out(resultado)


@router.put("/usuarios/{usuario_id}/estado", response_model=UsuarioAsignacionOut)
def actualizar_estado_usuario(
    usuario_id: str,
    payload: UsuarioEstadoUpdateRequest,
    _current_user: UserProfile = Depends(get_current_user),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: SetUsuarioActivoUseCase = Depends(get_set_usuario_activo_use_case),
):
    """
    Activa/desactiva un usuario (usuario.activo) en vez de borrarlo — CLAUDE.md §6 pide
    soft delete para usuarios. Un usuario inactivo conserva su rol/área asignados (por si
    se reactiva después) pero no puede volver a autenticarse (SyncUserRbacUseCase /
    get_current_user rechazan el login/las requests mientras esté inactivo).
    """
    resultado = use_case.execute(usuario_id, payload.activo, actor_id)
    return _usuario_to_out(resultado)
