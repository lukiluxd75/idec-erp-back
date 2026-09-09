from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.domains.seguridad.domain.entities.rbac import PermissionEntity, RoleEntity, UserEntity
from app.domains.seguridad.domain.ports.user_repository_port import UserRepositoryPort
from app.domains.seguridad.infrastructure.models import (
    AreaModel,
    PermisoModel,
    RolInternoModel,
    UsuarioModel,
    UsuarioRolAreaModel,
)

# Área + rol con los que arranca todo usuario nuevo autenticado por Keycloak: en vez de
# quedar sin permisos hasta que un admin se lo asigne a mano (CLAUDE.md §5 original), todo
# el que se loguea por primera vez entra por Catastro con el rol base "Inicio". Se
# resuelven con get-or-create (mismo patrón que
# SqlRbacAdminRepository._get_or_create_permiso) porque hoy no hay Alembic ni seed
# separado del código (CLAUDE.md §6): si el área o el rol ya existen (creados a mano desde
# RolesPage) se reusan tal cual, nunca se duplican por nombre.
AREA_INICIAL_NOMBRE = "Catastro"
ROL_INICIAL_NOMBRE = "Inicio"


class SqlUserRepository(UserRepositoryPort):
    """
    Adaptador de repositorio que implementa UserRepositoryPort usando SQLAlchemy contra
    el esquema real de PostgreSQL (creado con SQL puro por el equipo de base de datos,
    ver ecosistema_seguridad_backup.sql).
    """

    def __init__(self, db: Session):
        self._db = db

    def get_by_keycloak_sub(self, keycloak_sub: str) -> Optional[UserEntity]:
        user_model = (
            self._db.query(UsuarioModel)
            .filter(UsuarioModel.keycloak_sub == keycloak_sub)
            .first()
        )
        return self._to_entity(user_model) if user_model else None

    def ensure_user_exists(
        self, keycloak_sub: str, username: str, correo: Optional[str] = None
    ) -> UserEntity:
        user_model = (
            self._db.query(UsuarioModel)
            .filter(UsuarioModel.keycloak_sub == keycloak_sub)
            .first()
        )
        es_nuevo = user_model is None
        if es_nuevo:
            user_model = UsuarioModel(keycloak_sub=keycloak_sub, username=username, correo=correo)
            self._db.add(user_model)
            self._db.flush()
        else:
            user_model.username = username
            if correo:
                user_model.correo = correo

        if es_nuevo:
            area = self._get_or_create_area_inicial()
            rol = self._get_or_create_rol_inicial()
            self._db.add(UsuarioRolAreaModel(usuario_id=user_model.id, rol_id=rol.id, area_id=area.id))

        self._db.commit()
        self._db.refresh(user_model)
        return self._to_entity(user_model)

    def _get_or_create_area_inicial(self) -> AreaModel:
        area = self._db.query(AreaModel).filter(AreaModel.nombre == AREA_INICIAL_NOMBRE).first()
        if not area:
            area = AreaModel(nombre=AREA_INICIAL_NOMBRE)
            self._db.add(area)
            self._db.flush()
        return area

    def _get_or_create_rol_inicial(self) -> RolInternoModel:
        rol = self._db.query(RolInternoModel).filter(RolInternoModel.nombre == ROL_INICIAL_NOMBRE).first()
        if not rol:
            rol = RolInternoModel(
                nombre=ROL_INICIAL_NOMBRE,
                descripcion="Rol base con el que arranca todo usuario nuevo autenticado por Keycloak.",
            )
            self._db.add(rol)
            self._db.flush()
        return rol

    def get_user_permissions(self, keycloak_sub: str) -> List[str]:
        user_model = (
            self._db.query(UsuarioModel)
            .options(
                joinedload(UsuarioModel.asignaciones)
                .joinedload(UsuarioRolAreaModel.rol)
                .joinedload(RolInternoModel.permisos)
                .joinedload(PermisoModel.recurso)
            )
            .filter(UsuarioModel.keycloak_sub == keycloak_sub)
            .first()
        )
        if not user_model:
            return []

        codigos = set()
        for asignacion in user_model.asignaciones:
            rol = asignacion.rol
            if not rol or not rol.activo:
                continue
            for permiso in rol.permisos:
                entity = PermissionEntity(
                    id_permiso=str(permiso.id),
                    accion=permiso.accion,
                    recurso=permiso.recurso.nombre if permiso.recurso else None,
                    descripcion=permiso.descripcion,
                )
                codigos.add(entity.codigo)

        return sorted(codigos)

    def _to_entity(self, model: UsuarioModel) -> UserEntity:
        roles_entities = [
            RoleEntity(
                id_rol=str(asignacion.rol.id),
                nombre=asignacion.rol.nombre,
                descripcion=asignacion.rol.descripcion,
                activo=asignacion.rol.activo,
            )
            for asignacion in model.asignaciones
            if asignacion.rol
        ]
        return UserEntity(
            id_usuario=str(model.id),
            username=model.username,
            keycloak_sub=model.keycloak_sub,
            correo=model.correo,
            activo=model.activo,
            roles=roles_entities,
        )
