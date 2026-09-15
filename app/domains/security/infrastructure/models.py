"""
ORM models mirroring the REAL PostgreSQL schema for the security/RBAC module.

Python attributes and physical table/column names are English
(migrated via scripts/migrate_schema_to_english.py).

Permission hierarchy: systems -> subsystems -> resources -> permissions.
An internal role is always assigned to a user together with a concrete area
(user_role_areas) — there is no user<->role assignment without area.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database.connection import Base


def _uuid_pk() -> Column:
    return Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _created_at_column() -> Column:
    return Column(DateTime, server_default=text("now()"))


def _updated_at_column() -> Column:
    return Column(DateTime, server_default=text("now()"))


class SystemModel(Base):
    __tablename__ = "systems"

    id = _uuid_pk()
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, server_default=text("true"))
    description = Column(String(255))
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    subsystems = relationship("SubsystemModel", back_populates="system", cascade="all, delete-orphan")


class SubsystemModel(Base):
    __tablename__ = "subsystems"

    id = _uuid_pk()
    system_id = Column(UUID(as_uuid=True), ForeignKey("systems.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, server_default=text("true"))
    is_optional = Column(Boolean, server_default=text("false"))
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    system = relationship("SystemModel", back_populates="subsystems")
    resources = relationship("ResourceModel", back_populates="subsystem", cascade="all, delete-orphan")


class ResourceModel(Base):
    __tablename__ = "resources"

    id = _uuid_pk()
    subsystem_id = Column(UUID(as_uuid=True), ForeignKey("subsystems.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    endpoint_path = Column(String(200))
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    subsystem = relationship("SubsystemModel", back_populates="resources")
    permissions = relationship("PermissionModel", back_populates="resource", cascade="all, delete-orphan")


class UserModel(Base):
    """`keycloak_sub` links to JWT.sub. New users start with user_role_areas
    (area Catastro + role Inicio) via SqlUserRepository.ensure_user_exists."""

    __tablename__ = "users"

    id = _uuid_pk()
    keycloak_sub = Column(String(100), unique=True)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100))
    is_active = Column(Boolean, server_default=text("true"))
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    assignments = relationship("UserRoleAreaModel", back_populates="user", cascade="all, delete-orphan")


class AreaModel(Base):
    __tablename__ = "areas"

    id = _uuid_pk()
    name = Column(String(100), nullable=False)
    area_type = Column(String(50))
    created_at = _created_at_column()
    updated_at = _updated_at_column()


class InternalRoleModel(Base):
    """Internal role is separate from Keycloak roles."""

    __tablename__ = "internal_roles"

    id = _uuid_pk()
    name = Column(String(50), nullable=False)
    description = Column(String(150))
    is_active = Column(Boolean, server_default=text("true"))
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    assignments = relationship("UserRoleAreaModel", back_populates="role")
    permissions = relationship("PermissionModel", secondary="role_permissions", back_populates="roles")


class UserRoleAreaModel(Base):
    """Assigns an internal role to a user within a concrete area."""

    __tablename__ = "user_role_areas"

    id = _uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("internal_roles.id", ondelete="CASCADE"), nullable=False)
    area_id = Column(UUID(as_uuid=True), ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    created_at = _created_at_column()

    user = relationship("UserModel", back_populates="assignments")
    role = relationship("InternalRoleModel", back_populates="assignments")
    area = relationship("AreaModel")


class PermissionModel(Base):
    """Permission = action on a concrete resource (resource_id + action)."""

    __tablename__ = "permissions"

    id = _uuid_pk()
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(50), nullable=False)
    description = Column(String(150))
    created_at = _created_at_column()

    resource = relationship("ResourceModel", back_populates="permissions")
    roles = relationship("InternalRoleModel", secondary="role_permissions", back_populates="permissions")


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"

    id = _uuid_pk()
    role_id = Column(UUID(as_uuid=True), ForeignKey("internal_roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    created_at = _created_at_column()


class AccessAuditModel(Base):
    __tablename__ = "access_audits"

    id = _uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    role_id = Column(UUID(as_uuid=True), ForeignKey("internal_roles.id"))
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id"))
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id"))
    action = Column(String(50))
    allowed = Column(Boolean)
    timestamp = Column(DateTime, server_default=text("now()"))
    source_ip = Column(String(45))
    description = Column(String(255))


class GeoocrAuditModel(Base):
    __tablename__ = "geoocr_audits"

    id = _uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    description = Column(String(255))
    timestamp = Column(DateTime, server_default=text("now()"))
