from typing import Optional
from fastapi import APIRouter, Depends

from app.domains.security.domain.entities.user import UserProfile
from app.domains.security.application.use_cases import (
    ListRolesUseCase,
    CreateRoleUseCase,
    SetRolePermissionsUseCase,
    DeleteRoleUseCase,
    ListAreasUseCase,
    CreateAreaUseCase,
    UpdateAreaUseCase,
    DeleteAreaUseCase,
    ListUserAssignmentsUseCase,
    AssignRoleAreaUseCase,
    SetUserActiveUseCase,
)
from app.domains.security.presentation.deps import (
    get_current_usuario_id,
    get_list_roles_use_case,
    get_create_role_use_case,
    get_set_role_permissions_use_case,
    get_delete_role_use_case,
    get_list_areas_use_case,
    get_create_area_use_case,
    get_update_area_use_case,
    get_delete_area_use_case,
    get_list_user_assignments_use_case,
    get_assign_role_area_use_case,
    get_set_user_active_use_case,
    require_permission,
)
from app.domains.security.presentation.schemas.rbac_admin_schema import (
    RoleOut,
    RoleCreateRequest,
    RolePermissionsUpdateRequest,
    RoleSummaryOut,
    AreaOut,
    AreaCreateRequest,
    AreaUpdateRequest,
    UserAssignmentOut,
    AssignRoleAreaRequest,
    UserStatusUpdateRequest,
)
from app.domains.security.presentation.schemas.auth_schema import PublicMessageResponse

# Reads require security.view; mutations require security.edit (IDEC guide §8).
router = APIRouter(tags=["Security — Roles and Permissions"])


def _role_to_out(entity) -> RoleOut:
    # Out schemas keep Spanish JSON keys for frontend compatibility.
    return RoleOut(
        id=entity.role_id,
        nombre=entity.name,
        descripcion=entity.description,
        activo=entity.is_active,
        permisos=[permission.code for permission in entity.permissions],
    )


def _area_to_out(entity) -> AreaOut:
    return AreaOut(id=entity.area_id, nombre=entity.name, tipo=entity.area_type)


def _user_to_out(entity) -> UserAssignmentOut:
    return UserAssignmentOut(
        id=entity.user_id,
        username=entity.username,
        correo=entity.email,
        roles=[RoleSummaryOut(id=role.role_id, nombre=role.name) for role in entity.roles],
        area_id=entity.area_id,
        area_nombre=entity.area_name,
        activo=entity.is_active,
    )


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    _current_user: UserProfile = Depends(require_permission("security.view")),
    use_case: ListRolesUseCase = Depends(get_list_roles_use_case),
):
    return [_role_to_out(role) for role in use_case.execute()]


@router.post("/roles", response_model=RoleOut)
def create_role(
    payload: RoleCreateRequest,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    create_use_case: CreateRoleUseCase = Depends(get_create_role_use_case),
    set_permissions_use_case: SetRolePermissionsUseCase = Depends(get_set_role_permissions_use_case),
):
    role = create_use_case.execute(payload.nombre.strip())
    if payload.permisos:
        role = set_permissions_use_case.execute(role.role_id, payload.permisos, actor_id)
    return _role_to_out(role)


@router.put("/roles/{role_id}/permissions", response_model=RoleOut)
def update_role_permissions(
    role_id: str,
    payload: RolePermissionsUpdateRequest,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: SetRolePermissionsUseCase = Depends(get_set_role_permissions_use_case),
):
    role = use_case.execute(role_id, payload.permisos, actor_id)
    return _role_to_out(role)


@router.delete("/roles/{role_id}", response_model=PublicMessageResponse)
def delete_role(
    role_id: str,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: DeleteRoleUseCase = Depends(get_delete_role_use_case),
):
    use_case.execute(role_id, actor_id)
    return PublicMessageResponse(message="Rol eliminado correctamente.")


@router.get("/areas", response_model=list[AreaOut])
def list_areas(
    _current_user: UserProfile = Depends(require_permission("security.view")),
    use_case: ListAreasUseCase = Depends(get_list_areas_use_case),
):
    return [_area_to_out(area) for area in use_case.execute()]


@router.post("/areas", response_model=AreaOut)
def create_area(
    payload: AreaCreateRequest,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    use_case: CreateAreaUseCase = Depends(get_create_area_use_case),
):
    return _area_to_out(use_case.execute(payload.nombre.strip()))


@router.put("/areas/{area_id}", response_model=AreaOut)
def update_area(
    area_id: str,
    payload: AreaUpdateRequest,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    use_case: UpdateAreaUseCase = Depends(get_update_area_use_case),
):
    return _area_to_out(use_case.execute(area_id, payload.nombre.strip()))


@router.delete("/areas/{area_id}", response_model=PublicMessageResponse)
def delete_area(
    area_id: str,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: DeleteAreaUseCase = Depends(get_delete_area_use_case),
):
    use_case.execute(area_id, actor_id)
    return PublicMessageResponse(message="Área eliminada correctamente.")


@router.get("/users", response_model=list[UserAssignmentOut])
def list_users(
    _current_user: UserProfile = Depends(require_permission("security.view")),
    use_case: ListUserAssignmentsUseCase = Depends(get_list_user_assignments_use_case),
):
    return [_user_to_out(user) for user in use_case.execute()]


@router.put("/users/{user_id}/assignment", response_model=UserAssignmentOut)
def assign_role_area(
    user_id: str,
    payload: AssignRoleAreaRequest,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: AssignRoleAreaUseCase = Depends(get_assign_role_area_use_case),
):
    result = use_case.execute(user_id, payload.role_ids, payload.area_id, actor_id)
    return _user_to_out(result)


@router.put("/users/{user_id}/status", response_model=UserAssignmentOut)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    _current_user: UserProfile = Depends(require_permission("security.edit")),
    actor_id: Optional[str] = Depends(get_current_usuario_id),
    use_case: SetUserActiveUseCase = Depends(get_set_user_active_use_case),
):
    """
    Activate/deactivate a user (users.is_active) instead of deleting.
    Inactive users keep role/area but cannot authenticate.
    """
    result = use_case.execute(user_id, payload.activo, actor_id)
    return _user_to_out(result)
