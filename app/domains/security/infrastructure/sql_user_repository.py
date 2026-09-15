from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.domains.security.domain.entities.rbac import PermissionEntity, RoleEntity, UserEntity
from app.domains.security.domain.ports.user_repository_port import UserRepositoryPort
from app.domains.security.infrastructure.models import (
    AreaModel,
    PermissionModel,
    InternalRoleModel,
    UserModel,
    UserRoleAreaModel,
)

# Area + role every new Keycloak-authenticated user starts with: instead of
# having no permissions until an admin assigns them by hand (CLAUDE.md §5),
# everyone who logs in for the first time enters Catastro with the base "Inicio"
# role. Resolved via get-or-create (same pattern as
# SqlRbacAdminRepository._get_or_create_permission) because there is no Alembic
# or seed separate from the code today (CLAUDE.md §6): if the area or role already
# exists (created by hand from RolesPage) they are reused, never duplicated by name.
INITIAL_AREA_NAME = "Catastro"
INITIAL_ROLE_NAME = "Inicio"


class SqlUserRepository(UserRepositoryPort):
    """
    Repository adapter implementing UserRepositoryPort with SQLAlchemy against
    the real PostgreSQL schema (created with raw SQL by the DB team, see
    ecosistema_seguridad_backup.sql).
    """

    def __init__(self, db: Session):
        self._db = db

    def get_by_keycloak_sub(self, keycloak_sub: str) -> Optional[UserEntity]:
        user_model = (
            self._db.query(UserModel)
            .filter(UserModel.keycloak_sub == keycloak_sub)
            .first()
        )
        return self._to_entity(user_model) if user_model else None

    def ensure_user_exists(
        self, keycloak_sub: str, username: str, email: Optional[str] = None
    ) -> UserEntity:
        user_model = (
            self._db.query(UserModel)
            .filter(UserModel.keycloak_sub == keycloak_sub)
            .first()
        )
        is_new = user_model is None
        if is_new:
            user_model = UserModel(keycloak_sub=keycloak_sub, username=username, email=email)
            self._db.add(user_model)
            self._db.flush()
        else:
            user_model.username = username
            if email:
                user_model.email = email

        if is_new:
            area = self._get_or_create_initial_area()
            role = self._get_or_create_initial_role()
            self._db.add(UserRoleAreaModel(user_id=user_model.id, role_id=role.id, area_id=area.id))

        self._db.commit()
        self._db.refresh(user_model)
        return self._to_entity(user_model)

    def _get_or_create_initial_area(self) -> AreaModel:
        area = self._db.query(AreaModel).filter(AreaModel.name == INITIAL_AREA_NAME).first()
        if not area:
            area = AreaModel(name=INITIAL_AREA_NAME)
            self._db.add(area)
            self._db.flush()
        return area

    def _get_or_create_initial_role(self) -> InternalRoleModel:
        role = self._db.query(InternalRoleModel).filter(InternalRoleModel.name == INITIAL_ROLE_NAME).first()
        if not role:
            role = InternalRoleModel(
                name=INITIAL_ROLE_NAME,
                description="Rol base con el que arranca todo usuario nuevo autenticado por Keycloak.",
            )
            self._db.add(role)
            self._db.flush()
        return role

    def get_user_permissions(self, keycloak_sub: str) -> List[str]:
        user_model = (
            self._db.query(UserModel)
            .options(
                joinedload(UserModel.assignments)
                .joinedload(UserRoleAreaModel.role)
                .joinedload(InternalRoleModel.permissions)
                .joinedload(PermissionModel.resource)
            )
            .filter(UserModel.keycloak_sub == keycloak_sub)
            .first()
        )
        if not user_model:
            return []

        codes = set()
        for assignment in user_model.assignments:
            role = assignment.role
            if not role or not role.is_active:
                continue
            for permission in role.permissions:
                entity = PermissionEntity(
                    permission_id=str(permission.id),
                    action=permission.action,
                    resource=permission.resource.name if permission.resource else None,
                    description=permission.description,
                )
                codes.add(entity.code)

        return sorted(codes)

    def _to_entity(self, model: UserModel) -> UserEntity:
        role_entities = [
            RoleEntity(
                role_id=str(assignment.role.id),
                name=assignment.role.name,
                description=assignment.role.description,
                is_active=assignment.role.is_active,
            )
            for assignment in model.assignments
            if assignment.role
        ]
        return UserEntity(
            user_id=str(model.id),
            username=model.username,
            keycloak_sub=model.keycloak_sub,
            email=model.email,
            is_active=model.is_active,
            roles=role_entities,
        )
