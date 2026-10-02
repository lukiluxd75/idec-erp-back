from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database.connection import Base

SCHEMA = "cadastralviewer"


def _uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


class CadastralProcedureModel(Base):
    __tablename__ = "cadastral_procedure"
    __table_args__ = (
        UniqueConstraint("code", name="uq_cadastral_procedure_code"),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_cadastral_procedure_status"),
        Index("ix_cadastral_procedure_status_order", "status", "display_order"),
        {"schema": SCHEMA},
    )

    id = _uuid_pk()
    code = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(100), nullable=False, server_default=text("'services'"))
    icon = Column(String(32), nullable=False, server_default=text("'📋'"))
    requirements = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    estimated_days = Column(String(100))
    location = Column(String(255))
    status = Column(String(20), nullable=False, server_default=text("'draft'"))
    display_order = Column(Integer, nullable=False, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_by = Column(String(100), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_by = Column(String(100))
    deleted_at = Column(DateTime(timezone=True))


class MapLayerModel(Base):
    __tablename__ = "map_layer"
    __table_args__ = (
        UniqueConstraint("code", name="uq_map_layer_code"),
        CheckConstraint("layer_type IN ('imagery', 'vector')", name="ck_map_layer_type"),
        CheckConstraint("service_type IN ('wms')", name="ck_map_layer_service_type"),
        CheckConstraint("year IS NULL OR year BETWEEN 1900 AND 2200", name="ck_map_layer_year"),
        Index("ix_map_layer_active_order", "is_active", "display_order"),
        {"schema": SCHEMA},
    )

    id = _uuid_pk()
    code = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    layer_type = Column(String(20), nullable=False)
    service_type = Column(String(20), nullable=False, server_default=text("'wms'"))
    service_url = Column(Text, nullable=False)
    service_layer = Column(String(255), nullable=False, server_default=text("'0'"))
    year = Column(Integer)
    source = Column(String(255))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    display_order = Column(Integer, nullable=False, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_by = Column(String(100))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_by = Column(String(100))
    deleted_at = Column(DateTime(timezone=True))


class AdvertisementModel(Base):
    __tablename__ = "advertisement"
    __table_args__ = (
        CheckConstraint("source_type IN ('upload', 'url')", name="ck_advertisement_source_type"),
        CheckConstraint(
            "(source_type = 'upload' AND source_url IS NULL AND original_file_name IS NOT NULL "
            "AND storage_key IS NOT NULL AND mime_type IS NOT NULL AND file_size IS NOT NULL AND file_size > 0) "
            "OR (source_type = 'url' AND source_url IS NOT NULL AND original_file_name IS NULL "
            "AND storage_key IS NULL AND mime_type IS NULL AND file_size IS NULL)",
            name="ck_advertisement_source",
        ),
        Index("ix_advertisement_active_order", "is_active", "display_order"),
        {"schema": SCHEMA},
    )

    id = _uuid_pk()
    title = Column(String(255), nullable=False)
    source_type = Column(String(20), nullable=False)
    source_url = Column(Text)
    original_file_name = Column(String(255))
    storage_key = Column(String(255), unique=True)
    mime_type = Column(String(100))
    file_size = Column(BigInteger)
    is_active = Column(Boolean, nullable=False, server_default=text("false"))
    display_order = Column(Integer, nullable=False, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_by = Column(String(100), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_by = Column(String(100))
    deleted_at = Column(DateTime(timezone=True))
