from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.domains.seguridad.domain.entities.rbac import (
    AreaEntity,
    PermissionEntity,
    RoleEntity,
    UsuarioAsignacionEntity,
)
from app.domains.seguridad.domain.ports.rbac_admin_repository_port import RbacAdminRepositoryPort
from app.domains.seguridad.infrastructure.models import (
    AreaModel,
    AuditoriaAccesoModel,
    PermisoModel,
    RecursoModel,
    RolInternoModel,
    RolPermisoModel,
    SistemaModel,
    SubsistemaModel,
    UsuarioModel,
    UsuarioRolAreaModel,
)

# Nombres del sistema/subsistema donde viven los recursos que representan los módulos
# del ERP (uno por módulo de negocio, ej. 'geoextraccion', 'seguridad'). El catálogo de
# módulos en sí no lo define el backend: lo manda el frontend (derivado de NAV_SECTIONS,
# ver Frontend/src/domains/seguridad/data/mockSeguridad.js) al asignar permisos a un rol;
# acá solo se garantiza que cada módulo usado tenga su fila real en 'recurso'/'permiso'
# (CLAUDE.md §4: nunca un permiso implícito sin fila en la tabla).
_SISTEMA_NOMBRE = "ERP Catastro"
_SUBSISTEMA_NOMBRE = "Módulos ERP"


class SqlRbacAdminRepository(RbacAdminRepositoryPort):
    """Adaptador de RbacAdminRepositoryPort contra el esquema real de PostgreSQL."""

    def __init__(self, db: Session):
        self._db = db

    # --- roles -----------------------------------------------------------------

    def list_roles(self) -> List[RoleEntity]:
        roles = (
            self._db.query(RolInternoModel)
            .options(joinedload(RolInternoModel.permisos).joinedload(PermisoModel.recurso))
            .filter(RolInternoModel.activo.is_(True))
            .order_by(RolInternoModel.nombre)
            .all()
        )
        return [self._role_to_entity(rol) for rol in roles]

    def create_role(self, nombre: str) -> RoleEntity:
        rol = RolInternoModel(nombre=nombre)
        self._db.add(rol)
        self._db.commit()
        self._db.refresh(rol)
        return self._role_to_entity(rol)

    def set_role_permissions(self, rol_id: str, codigos: List[str], actor_usuario_id: Optional[str]) -> RoleEntity:
        rol = self._db.query(RolInternoModel).filter(RolInternoModel.id == rol_id).first()
        if not rol:
            raise ValueError(f"No existe el rol '{rol_id}'.")

        permisos = [self._get_or_create_permiso(codigo) for codigo in codigos]

        self._db.query(RolPermisoModel).filter(RolPermisoModel.rol_id == rol_id).delete()
        for permiso in permisos:
            self._db.add(RolPermisoModel(rol_id=rol.id, permiso_id=permiso.id))
        self._db.commit()

        self._audit(actor_usuario_id, "rol.permisos.actualizar", f"Permisos de '{rol.nombre}' actualizados.")

        self._db.refresh(rol)
        rol = (
            self._db.query(RolInternoModel)
            .options(joinedload(RolInternoModel.permisos).joinedload(PermisoModel.recurso))
            .filter(RolInternoModel.id == rol_id)
            .first()
        )
        return self._role_to_entity(rol)

    def delete_role(self, rol_id: str, actor_usuario_id: Optional[str]) -> None:
        rol = self._db.query(RolInternoModel).filter(RolInternoModel.id == rol_id).first()
        if not rol:
            return
        nombre = rol.nombre
        self._db.delete(rol)
        self._db.commit()
        self._audit(actor_usuario_id, "rol.eliminar", f"Rol '{nombre}' eliminado.")

    # --- áreas -------------------------------------------------------------------

    def list_areas(self) -> List[AreaEntity]:
        areas = self._db.query(AreaModel).order_by(AreaModel.nombre).all()
        return [self._area_to_entity(area) for area in areas]

    def create_area(self, nombre: str) -> AreaEntity:
        area = AreaModel(nombre=nombre)
        self._db.add(area)
        self._db.commit()
        self._db.refresh(area)
        return self._area_to_entity(area)

    def update_area(self, area_id: str, nombre: str) -> AreaEntity:
        area = self._db.query(AreaModel).filter(AreaModel.id == area_id).first()
        if not area:
            raise ValueError(f"No existe el área '{area_id}'.")
        area.nombre = nombre
        self._db.commit()
        self._db.refresh(area)
        return self._area_to_entity(area)

    def delete_area(self, area_id: str, actor_usuario_id: Optional[str]) -> None:
        area = self._db.query(AreaModel).filter(AreaModel.id == area_id).first()
        if not area:
            return
        nombre = area.nombre
        self._db.delete(area)
        self._db.commit()
        self._audit(actor_usuario_id, "area.eliminar", f"Área '{nombre}' eliminada.")

    # --- usuarios / asignación rol+área ------------------------------------------

    def list_usuarios_con_asignacion(self) -> List[UsuarioAsignacionEntity]:
        usuarios = (
            self._db.query(UsuarioModel)
            .options(
                joinedload(UsuarioModel.asignaciones).joinedload(UsuarioRolAreaModel.rol),
                joinedload(UsuarioModel.asignaciones).joinedload(UsuarioRolAreaModel.area),
            )
            .order_by(UsuarioModel.activo.desc(), UsuarioModel.username)
            .all()
        )
        return [self._usuario_to_entity(usuario) for usuario in usuarios]

    def asignar_rol_area(
        self,
        usuario_id: str,
        rol_ids: List[str],
        area_id: Optional[str],
        actor_usuario_id: Optional[str],
    ) -> UsuarioAsignacionEntity:
        usuario = self._db.query(UsuarioModel).filter(UsuarioModel.id == usuario_id).first()
        if not usuario:
            raise ValueError(f"No existe el usuario '{usuario_id}'.")

        self._db.query(UsuarioRolAreaModel).filter(UsuarioRolAreaModel.usuario_id == usuario_id).delete()

        if area_id:
            for rol_id in dict.fromkeys(rol_ids):  # dedupe preservando orden
                self._db.add(UsuarioRolAreaModel(usuario_id=usuario.id, rol_id=rol_id, area_id=area_id))

        self._db.commit()
        self._audit(
            actor_usuario_id,
            "usuario.rol_area.asignar",
            f"Asignación de rol/área de '{usuario.username}' actualizada.",
        )

        usuario = (
            self._db.query(UsuarioModel)
            .options(
                joinedload(UsuarioModel.asignaciones).joinedload(UsuarioRolAreaModel.rol),
                joinedload(UsuarioModel.asignaciones).joinedload(UsuarioRolAreaModel.area),
            )
            .filter(UsuarioModel.id == usuario_id)
            .first()
        )
        return self._usuario_to_entity(usuario)

    def set_usuario_activo(
        self, usuario_id: str, activo: bool, actor_usuario_id: Optional[str]
    ) -> UsuarioAsignacionEntity:
        usuario = self._db.query(UsuarioModel).filter(UsuarioModel.id == usuario_id).first()
        if not usuario:
            raise ValueError(f"No existe el usuario '{usuario_id}'.")

        usuario.activo = activo
        self._db.commit()
        self._audit(
            actor_usuario_id,
            "usuario.activo.actualizar",
            f"Usuario '{usuario.username}' marcado como {'activo' if activo else 'inactivo'}.",
        )

        usuario = (
            self._db.query(UsuarioModel)
            .options(
                joinedload(UsuarioModel.asignaciones).joinedload(UsuarioRolAreaModel.rol),
                joinedload(UsuarioModel.asignaciones).joinedload(UsuarioRolAreaModel.area),
            )
            .filter(UsuarioModel.id == usuario_id)
            .first()
        )
        return self._usuario_to_entity(usuario)

    # --- helpers internos ---------------------------------------------------------

    def _get_or_create_permiso(self, codigo: str) -> PermisoModel:
        """Resuelve un código 'recurso.accion' a una fila real de 'permiso', creando el
        'recurso' (y el sistema/subsistema contenedor si hace falta) la primera vez que
        se usa un módulo."""
        recurso_nombre, _, accion = codigo.partition(".")
        if not accion:
            raise ValueError(f"Código de permiso inválido: '{codigo}' (se espera 'recurso.accion').")

        recurso = (
            self._db.query(RecursoModel)
            .join(SubsistemaModel)
            .join(SistemaModel)
            .filter(
                RecursoModel.nombre == recurso_nombre,
                SubsistemaModel.nombre == _SUBSISTEMA_NOMBRE,
                SistemaModel.nombre == _SISTEMA_NOMBRE,
            )
            .first()
        )
        if not recurso:
            recurso = RecursoModel(nombre=recurso_nombre, subsistema_id=self._get_or_create_subsistema().id)
            self._db.add(recurso)
            self._db.flush()

        permiso = (
            self._db.query(PermisoModel)
            .filter(PermisoModel.recurso_id == recurso.id, PermisoModel.accion == accion)
            .first()
        )
        if not permiso:
            permiso = PermisoModel(recurso_id=recurso.id, accion=accion)
            self._db.add(permiso)
            self._db.flush()

        return permiso

    def _get_or_create_subsistema(self) -> SubsistemaModel:
        sistema = self._db.query(SistemaModel).filter(SistemaModel.nombre == _SISTEMA_NOMBRE).first()
        if not sistema:
            sistema = SistemaModel(nombre=_SISTEMA_NOMBRE, descripcion="Catálogo de módulos del ERP para RBAC.")
            self._db.add(sistema)
            self._db.flush()

        subsistema = (
            self._db.query(SubsistemaModel)
            .filter(SubsistemaModel.nombre == _SUBSISTEMA_NOMBRE, SubsistemaModel.sistema_id == sistema.id)
            .first()
        )
        if not subsistema:
            subsistema = SubsistemaModel(nombre=_SUBSISTEMA_NOMBRE, sistema_id=sistema.id)
            self._db.add(subsistema)
            self._db.flush()

        return subsistema

    def _audit(self, actor_usuario_id: Optional[str], accion: str, descripcion: str) -> None:
        """Deja constancia en auditoria_acceso de una escritura administrativa RBAC
        (CLAUDE.md §9: toda escritura de negocio queda auditada)."""
        self._db.add(
            AuditoriaAccesoModel(
                usuario_id=actor_usuario_id,
                accion=accion,
                permitido=True,
                descripcion=descripcion,
            )
        )
        self._db.commit()

    @staticmethod
    def _role_to_entity(rol: RolInternoModel) -> RoleEntity:
        permisos = [
            PermissionEntity(
                id_permiso=str(permiso.id),
                accion=permiso.accion,
                recurso=permiso.recurso.nombre if permiso.recurso else None,
                descripcion=permiso.descripcion,
            )
            for permiso in rol.permisos
        ]
        return RoleEntity(
            id_rol=str(rol.id),
            nombre=rol.nombre,
            descripcion=rol.descripcion,
            activo=rol.activo,
            permisos=permisos,
        )

    @staticmethod
    def _area_to_entity(area: AreaModel) -> AreaEntity:
        return AreaEntity(id_area=str(area.id), nombre=area.nombre, tipo=area.tipo)

    @staticmethod
    def _usuario_to_entity(usuario: UsuarioModel) -> UsuarioAsignacionEntity:
        asignaciones = [a for a in usuario.asignaciones if a.rol]
        primera = asignaciones[0] if asignaciones else None
        return UsuarioAsignacionEntity(
            id_usuario=str(usuario.id),
            username=usuario.username,
            correo=usuario.correo,
            roles=[
                RoleEntity(id_rol=str(a.rol_id), nombre=a.rol.nombre, activo=a.rol.activo)
                for a in asignaciones
            ],
            area_id=str(primera.area_id) if primera else None,
            area_nombre=primera.area.nombre if primera and primera.area else None,
            activo=usuario.activo,
        )
