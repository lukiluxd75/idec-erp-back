"""
Modelos ORM que reflejan el esquema REAL de PostgreSQL, tal como lo crea el equipo de
base de datos con SQL puro (ver ecosistema_seguridad_backup.sql en la raíz del repo).
Este archivo no define el esquema — lo describe. Si el equipo de base de datos cambia
una tabla, este archivo se actualiza para que coincida, no al revés.

Jerarquía de permisos: sistema -> subsistema -> recurso -> permiso (accion sobre ese
recurso). Un rol_interno se asigna a un usuario siempre junto con un área concreta
(tabla usuario_rol_area) — no existe una asignación usuario<->rol sin área.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database.connection import Base


def _uuid_pk() -> Column:
    return Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _fecha_creacion() -> Column:
    return Column(DateTime, server_default=text("now()"))


def _fecha_actualizacion() -> Column:
    return Column(DateTime, server_default=text("now()"))


class SistemaModel(Base):
    __tablename__ = "sistema"

    id = _uuid_pk()
    nombre = Column(String(100), nullable=False)
    activo = Column(Boolean, server_default=text("true"))
    descripcion = Column(String(255))
    fecha_creacion = _fecha_creacion()
    fecha_actualizacion = _fecha_actualizacion()

    subsistemas = relationship("SubsistemaModel", back_populates="sistema", cascade="all, delete-orphan")


class SubsistemaModel(Base):
    __tablename__ = "subsistema"

    id = _uuid_pk()
    sistema_id = Column(UUID(as_uuid=True), ForeignKey("sistema.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(100), nullable=False)
    activo = Column(Boolean, server_default=text("true"))
    es_opcional = Column(Boolean, server_default=text("false"))
    fecha_creacion = _fecha_creacion()
    fecha_actualizacion = _fecha_actualizacion()

    sistema = relationship("SistemaModel", back_populates="subsistemas")
    recursos = relationship("RecursoModel", back_populates="subsistema", cascade="all, delete-orphan")


class RecursoModel(Base):
    __tablename__ = "recurso"

    id = _uuid_pk()
    subsistema_id = Column(UUID(as_uuid=True), ForeignKey("subsistema.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(100), nullable=False)
    ruta_endpoint = Column(String(200))
    fecha_creacion = _fecha_creacion()
    fecha_actualizacion = _fecha_actualizacion()

    subsistema = relationship("SubsistemaModel", back_populates="recursos")
    permisos = relationship("PermisoModel", back_populates="recurso", cascade="all, delete-orphan")


class UsuarioModel(Base):
    """`keycloak_sub` es el vínculo con JWT.sub (CLAUDE.md §5). Un usuario nuevo arranca
    con una fila en usuario_rol_area — área "Catastro" + rol "Inicio" — asignada por
    SqlUserRepository.ensure_user_exists, no elegida en base a nada de Keycloak."""
    __tablename__ = "usuario"

    id = _uuid_pk()
    keycloak_sub = Column(String(100), unique=True)
    username = Column(String(50), nullable=False, unique=True)
    correo = Column(String(100))
    activo = Column(Boolean, server_default=text("true"))
    fecha_creacion = _fecha_creacion()
    fecha_actualizacion = _fecha_actualizacion()

    asignaciones = relationship("UsuarioRolAreaModel", back_populates="usuario", cascade="all, delete-orphan")


class AreaModel(Base):
    __tablename__ = "area"

    id = _uuid_pk()
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(50))
    fecha_creacion = _fecha_creacion()
    fecha_actualizacion = _fecha_actualizacion()


class RolInternoModel(Base):
    """Sin columna keycloak_id: un rol interno es un concepto separado de los roles de
    Keycloak (CLAUDE.md §5 y §6) — nunca se crea "para reflejar" un rol de Keycloak."""
    __tablename__ = "rol_interno"

    id = _uuid_pk()
    nombre = Column(String(50), nullable=False)
    descripcion = Column(String(150))
    activo = Column(Boolean, server_default=text("true"))
    fecha_creacion = _fecha_creacion()
    fecha_actualizacion = _fecha_actualizacion()

    asignaciones = relationship("UsuarioRolAreaModel", back_populates="rol")
    permisos = relationship("PermisoModel", secondary="rol_permiso", back_populates="roles")


class UsuarioRolAreaModel(Base):
    """Asigna un rol_interno a un usuario dentro de un área concreta. El área es
    obligatoria en la base real: no existe asignación usuario<->rol sin área (es el
    "alcance" del que habla CLAUDE.md §5)."""
    __tablename__ = "usuario_rol_area"

    id = _uuid_pk()
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    rol_id = Column(UUID(as_uuid=True), ForeignKey("rol_interno.id", ondelete="CASCADE"), nullable=False)
    area_id = Column(UUID(as_uuid=True), ForeignKey("area.id", ondelete="CASCADE"), nullable=False)
    fecha_creacion = _fecha_creacion()

    usuario = relationship("UsuarioModel", back_populates="asignaciones")
    rol = relationship("RolInternoModel", back_populates="asignaciones")
    area = relationship("AreaModel")


class PermisoModel(Base):
    """Un permiso es una acción sobre un recurso concreto (recurso_id + accion), no un
    nombre plano — aproxima el formato `dominio.recurso.accion` de CLAUDE.md §8, aunque
    el nivel "dominio" (sistema/subsistema aquí) todavía no está confirmado 1:1 con los
    dominios del ERP (Catastro, Seguridad...) — ver CLAUDE.md §10."""
    __tablename__ = "permiso"

    id = _uuid_pk()
    recurso_id = Column(UUID(as_uuid=True), ForeignKey("recurso.id", ondelete="CASCADE"), nullable=False)
    accion = Column(String(50), nullable=False)
    descripcion = Column(String(150))
    fecha_creacion = _fecha_creacion()

    recurso = relationship("RecursoModel", back_populates="permisos")
    roles = relationship("RolInternoModel", secondary="rol_permiso", back_populates="permisos")


class RolPermisoModel(Base):
    __tablename__ = "rol_permiso"

    id = _uuid_pk()
    rol_id = Column(UUID(as_uuid=True), ForeignKey("rol_interno.id", ondelete="CASCADE"), nullable=False)
    permiso_id = Column(UUID(as_uuid=True), ForeignKey("permiso.id", ondelete="CASCADE"), nullable=False)
    fecha_creacion = _fecha_creacion()


class AuditoriaAccesoModel(Base):
    __tablename__ = "auditoria_acceso"

    id = _uuid_pk()
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"))
    rol_id = Column(UUID(as_uuid=True), ForeignKey("rol_interno.id"))
    recurso_id = Column(UUID(as_uuid=True), ForeignKey("recurso.id"))
    permiso_id = Column(UUID(as_uuid=True), ForeignKey("permiso.id"))
    accion = Column(String(50))
    permitido = Column(Boolean)
    timestamp = Column(DateTime, server_default=text("now()"))
    ip_origen = Column(String(45))
    descripcion = Column(String(255))


class AuditoriaGeoocrModel(Base):
    __tablename__ = "auditoria_geoocr"

    id = _uuid_pk()
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False)
    accion = Column(String(50), nullable=False)
    descripcion = Column(String(255))
    timestamp = Column(DateTime, server_default=text("now()"))
