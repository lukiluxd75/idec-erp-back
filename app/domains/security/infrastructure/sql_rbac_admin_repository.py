from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.domains.security.domain.entities.rbac import (
    AreaEntity,
    PermissionEntity,
    RoleEntity,
    UserAssignmentEntity,
)
from app.domains.security.domain.ports.rbac_admin_repository_port import RbacAdminRepositoryPort
from app.domains.security.infrastructure.models import (
    AreaModel,
    AccessAuditModel,
    PermissionModel,
    ResourceModel,
    InternalRoleModel,
    RolePermissionModel,
    SystemModel,
    SubsystemModel,
    UserModel,
    UserRoleAreaModel,
)

# System/subsystem names that hold resources representing ERP modules (one per
# business module, e.g. 'geoextraction', 'security'). The module catalog itself
# is not defined by the backend: the frontend sends it (derived from NAV_SECTIONS,
# see Frontend/src/domains/seguridad/data/mockSeguridad.js) when assigning
# permissions to a role; here we only ensure each used module has a real row in
# 'recurso'/'permiso' (CLAUDE.md §4: never an implicit permission without a table row).
_SYSTEM_NAME = "ERP Catastro"
_SUBSYSTEM_NAME = "Módulos ERP"


class SqlRbacAdminRepository(RbacAdminRepositoryPort):
    """Adapter implementing RbacAdminRepositoryPort against the real PostgreSQL schema."""

    def __init__(self, db: Session):
        self._db = db

    # --- roles -----------------------------------------------------------------

    def list_roles(self) -> List[RoleEntity]:
        roles = (
            self._db.query(InternalRoleModel)
            .options(joinedload(InternalRoleModel.permissions).joinedload(PermissionModel.resource))
            .filter(InternalRoleModel.is_active.is_(True))
            .order_by(InternalRoleModel.name)
            .all()
        )
        return [self._role_to_entity(role) for role in roles]

    def create_role(self, name: str) -> RoleEntity:
        role = InternalRoleModel(name=name)
        self._db.add(role)
        self._db.commit()
        self._db.refresh(role)
        return self._role_to_entity(role)

    def set_role_permissions(self, role_id: str, codes: List[str], actor_user_id: Optional[str]) -> RoleEntity:
        role = self._db.query(InternalRoleModel).filter(InternalRoleModel.id == role_id).first()
        if not role:
            raise ValueError(f"No existe el rol '{role_id}'.")

        permissions = [self._get_or_create_permission(code) for code in codes]

        self._db.query(RolePermissionModel).filter(RolePermissionModel.role_id == role_id).delete()
        for permission in permissions:
            self._db.add(RolePermissionModel(role_id=role.id, permission_id=permission.id))
        self._db.commit()

        self._audit(actor_user_id, "rol.permissions.actualizar", f"Permisos de '{role.name}' actualizados.")

        self._db.refresh(role)
        role = (
            self._db.query(InternalRoleModel)
            .options(joinedload(InternalRoleModel.permissions).joinedload(PermissionModel.resource))
            .filter(InternalRoleModel.id == role_id)
            .first()
        )
        return self._role_to_entity(role)

    def delete_role(self, role_id: str, actor_user_id: Optional[str]) -> None:
        role = self._db.query(InternalRoleModel).filter(InternalRoleModel.id == role_id).first()
        if not role:
            return
        role_name = role.name
        self._db.delete(role)
        self._db.commit()
        self._audit(actor_user_id, "rol.eliminar", f"Rol '{role_name}' eliminado.")

    # --- areas -----------------------------------------------------------------

    def list_areas(self) -> List[AreaEntity]:
        areas = self._db.query(AreaModel).order_by(AreaModel.name).all()
        return [self._area_to_entity(area) for area in areas]

    def create_area(self, name: str) -> AreaEntity:
        area = AreaModel(name=name)
        self._db.add(area)
        self._db.commit()
        self._db.refresh(area)
        return self._area_to_entity(area)

    def update_area(self, area_id: str, name: str) -> AreaEntity:
        area = self._db.query(AreaModel).filter(AreaModel.id == area_id).first()
        if not area:
            raise ValueError(f"No existe el área '{area_id}'.")
        area.name = name
        self._db.commit()
        self._db.refresh(area)
        return self._area_to_entity(area)

    def delete_area(self, area_id: str, actor_user_id: Optional[str]) -> None:
        area = self._db.query(AreaModel).filter(AreaModel.id == area_id).first()
        if not area:
            return
        area_name = area.name
        self._db.delete(area)
        self._db.commit()
        self._audit(actor_user_id, "area.eliminar", f"Área '{area_name}' eliminada.")

    # --- users / role+area assignment ------------------------------------------

    def list_users_with_assignment(self) -> List[UserAssignmentEntity]:
        users = (
            self._db.query(UserModel)
            .options(
                joinedload(UserModel.assignments).joinedload(UserRoleAreaModel.role),
                joinedload(UserModel.assignments).joinedload(UserRoleAreaModel.area),
            )
            .order_by(UserModel.is_active.desc(), UserModel.username)
            .all()
        )
        return [self._user_to_entity(user) for user in users]

    def assign_role_area(
        self,
        user_id: str,
        role_ids: List[str],
        area_id: Optional[str],
        actor_user_id: Optional[str],
    ) -> UserAssignmentEntity:
        user = self._db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise ValueError(f"No existe el usuario '{user_id}'.")

        self._db.query(UserRoleAreaModel).filter(UserRoleAreaModel.user_id == user_id).delete()

        if area_id:
            for rid in dict.fromkeys(role_ids):  # dedupe preserving order
                self._db.add(UserRoleAreaModel(user_id=user.id, role_id=rid, area_id=area_id))

        self._db.commit()
        self._audit(
            actor_user_id,
            "usuario.role_area.asignar",
            f"Asignación de rol/área de '{user.username}' actualizada.",
        )

        user = (
            self._db.query(UserModel)
            .options(
                joinedload(UserModel.assignments).joinedload(UserRoleAreaModel.role),
                joinedload(UserModel.assignments).joinedload(UserRoleAreaModel.area),
            )
            .filter(UserModel.id == user_id)
            .first()
        )
        return self._user_to_entity(user)

    def set_user_active(
        self, user_id: str, is_active: bool, actor_user_id: Optional[str]
    ) -> UserAssignmentEntity:
        user = self._db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise ValueError(f"No existe el usuario '{user_id}'.")

        user.is_active = is_active
        self._db.commit()
        self._audit(
            actor_user_id,
            "usuario.is_active.actualizar",
            f"Usuario '{user.username}' marcado como {'activo' if is_active else 'inactivo'}.",
        )

        user = (
            self._db.query(UserModel)
            .options(
                joinedload(UserModel.assignments).joinedload(UserRoleAreaModel.role),
                joinedload(UserModel.assignments).joinedload(UserRoleAreaModel.area),
            )
            .filter(UserModel.id == user_id)
            .first()
        )
        return self._user_to_entity(user)

    # --- internal helpers ------------------------------------------------------

    def _get_or_create_permission(self, code: str) -> PermissionModel:
        """Resolve a 'resource.action' code to a real 'permiso' row, creating the
        'recurso' (and containing system/subsystem if needed) the first time a
        module is used."""
        resource_name, _, action = code.partition(".")
        if not action:
            raise ValueError(f"Código de permiso inválido: '{code}' (se espera 'recurso.action').")

        resource = (
            self._db.query(ResourceModel)
            .join(SubsystemModel)
            .join(SystemModel)
            .filter(
                ResourceModel.name == resource_name,
                SubsystemModel.name == _SUBSYSTEM_NAME,
                SystemModel.name == _SYSTEM_NAME,
            )
            .first()
        )
        if not resource:
            resource = ResourceModel(name=resource_name, subsystem_id=self._get_or_create_subsystem().id)
            self._db.add(resource)
            self._db.flush()

        permission = (
            self._db.query(PermissionModel)
            .filter(PermissionModel.resource_id == resource.id, PermissionModel.action == action)
            .first()
        )
        if not permission:
            permission = PermissionModel(resource_id=resource.id, action=action)
            self._db.add(permission)
            self._db.flush()

        return permission

    def _get_or_create_subsystem(self) -> SubsystemModel:
        system = self._db.query(SystemModel).filter(SystemModel.name == _SYSTEM_NAME).first()
        if not system:
            system = SystemModel(name=_SYSTEM_NAME, description="Catálogo de módulos del ERP para RBAC.")
            self._db.add(system)
            self._db.flush()

        subsystem = (
            self._db.query(SubsystemModel)
            .filter(SubsystemModel.name == _SUBSYSTEM_NAME, SubsystemModel.system_id == system.id)
            .first()
        )
        if not subsystem:
            subsystem = SubsystemModel(name=_SUBSYSTEM_NAME, system_id=system.id)
            self._db.add(subsystem)
            self._db.flush()

        return subsystem

    def _audit(self, actor_user_id: Optional[str], action: str, description: str) -> None:
        """Record an RBAC admin write in auditoria_acceso (CLAUDE.md §9: every
        business write is audited)."""
        self._db.add(
            AccessAuditModel(
                user_id=actor_user_id,
                action=action,
                allowed=True,
                description=description,
            )
        )
        self._db.commit()

    @staticmethod
    def _role_to_entity(role: InternalRoleModel) -> RoleEntity:
        permissions = [
            PermissionEntity(
                permission_id=str(permission.id),
                action=permission.action,
                resource=permission.resource.name if permission.resource else None,
                description=permission.description,
            )
            for permission in role.permissions
        ]
        return RoleEntity(
            role_id=str(role.id),
            name=role.name,
            description=role.description,
            is_active=role.is_active,
            permissions=permissions,
        )

    @staticmethod
    def _area_to_entity(area: AreaModel) -> AreaEntity:
        return AreaEntity(area_id=str(area.id), name=area.name, area_type=area.area_type)

    @staticmethod
    def _user_to_entity(user: UserModel) -> UserAssignmentEntity:
        assignments = [a for a in user.assignments if a.role]
        first = assignments[0] if assignments else None
        return UserAssignmentEntity(
            user_id=str(user.id),
            username=user.username,
            email=user.email,
            roles=[
                RoleEntity(role_id=str(a.role_id), name=a.role.name, is_active=a.role.is_active)
                for a in assignments
            ],
            area_id=str(first.area_id) if first else None,
            area_name=first.area.name if first and first.area else None,
            is_active=user.is_active,
        )
