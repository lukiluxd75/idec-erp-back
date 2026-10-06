"""
ORM models for the Plantillas Dinámicas module -- schema `plantillas_dinamicas`,
owned by this module (unlike `resolutions`, nothing external writes to it).

The schema/tables are defined in database/plantillas_dinamicas_postgresql.sql,
which is a migration PROPOSAL and is deliberately NOT auto-executed (see that
file's own header) -- run it by hand against the target Postgres before these
endpoints will work. Because of that, these models are NOT registered in
init_db_tables (see core/database/connection.py): until the SQL is run there is
nothing here for SQLAlchemy to create or query, same reasoning as
app/domains/resolutions/infrastructure/models.py for a schema this app does not
own outright.

`plantilla`, `variable` and the CITES trio (`cite_configuracion`,
`cite_correlativo`, `cite_generado`) are mapped here. `plantilla_variable`,
`documento_generado` and `historial_documento` stay in the SQL proposal for
now; map them here once a concrete use case needs them (actual document
generation/download still waits on the existing external service, per
DocumentsPage -- CITES is decoupled from that: a CITE can be reserved for a
`tramite_id` without a `documento_id` yet).
"""
from sqlalchemy import (
    DateTime,
    Identity,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.core.database.connection import Base

SCHEMA = "templates"


class TemplateModel(Base):
    __tablename__ = "templates"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    nombre = Column("name", String(200), nullable=False)
    codigo = Column("code", String(100), nullable=False, unique=True)
    area = Column("area", String(100), nullable=False)
    tipo_documento = Column("document_type", String(100), nullable=False)
    descripcion = Column("description", String(500))
    contenido_html = Column("html_content", Text, nullable=False)
    version = Column("version", Integer, nullable=False, server_default=text("1"))
    activa = Column("is_active", Boolean, nullable=False, server_default=text("true"))
    creado_en = Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"))
    actualizado_en = Column("updated_at", DateTime(timezone=True))
    creado_por = Column("created_by", String(255))
    actualizado_por = Column("updated_by", String(255))


class VariableModel(Base):
    __tablename__ = "variables"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    nombre = Column("name", String(150), nullable=False)
    clave = Column("key", String(100), nullable=False, unique=True)
    descripcion = Column("description", String(500))
    tipo_dato = Column("data_type", String(50), nullable=False)
    valor_predeterminado = Column("default_value", Text)
    activa = Column("is_active", Boolean, nullable=False, server_default=text("true"))
    creado_en = Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"))
    actualizado_en = Column("updated_at", DateTime(timezone=True))


class CiteConfiguracionModel(Base):
    """One 'sigla': a unique área + tipo_documento combination, its code format
    and whether its counter resets every gestion (year)."""

    __tablename__ = "cite_configurations"
    __table_args__ = (
        # Los nombres son los de la BASE, no los del atributo en Python: el
        # atributo `area_codigo` vive en la columna `area_code` (ver abajo), y
        # pedir la restricción sobre "area_codigo" rompe el import del dominio
        # entero con "no column named 'area_codigo' is present".
        UniqueConstraint("area_code", "document_type_code", name="uq_cite_configuracion"),
        CheckConstraint("number_length BETWEEN 1 AND 12", name="ck_cite_configuracion_longitud"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    area_codigo = Column("area_code", String(20), nullable=False)
    tipo_documento_codigo = Column("document_type_code", String(20), nullable=False)
    nombre = Column("name", String(150), nullable=False)
    formato = Column("format", String(150), nullable=False)
    longitud_numero = Column("number_length", SmallInteger, nullable=False, server_default=text("5"))
    reinicia_por_gestion = Column("resets_per_year", Boolean, nullable=False, server_default=text("true"))
    activa = Column("is_active", Boolean, nullable=False, server_default=text("true"))


class CiteCorrelativoModel(Base):
    """The actual counter: one row per (configuracion, gestion). Incremented
    under `SELECT ... FOR UPDATE` by SqlCiteRepository.generate() so concurrent
    requests never hand out the same número_correlativo."""

    __tablename__ = "cite_counters"
    __table_args__ = (
        CheckConstraint("year BETWEEN 2000 AND 9999", name="ck_cite_correlativo_gestion"),
        CheckConstraint("last_number >= 0", name="ck_cite_correlativo_numero"),
        {"schema": SCHEMA},
    )

    cite_configuracion_id = Column("cite_configuration_id", 
        BigInteger, ForeignKey(f"{SCHEMA}.cite_configurations.id"), primary_key=True
    )
    gestion = Column("year", Integer, primary_key=True)
    ultimo_numero = Column("last_number", Integer, nullable=False, server_default=text("0"))


class CiteGeneradoModel(Base):
    __tablename__ = "generated_cites"
    __table_args__ = (
        UniqueConstraint(
            "cite_configuration_id", "year", "correlative_number", name="uq_cite_numero_por_gestion"
        ),
        CheckConstraint("year BETWEEN 2000 AND 9999", name="ck_cite_generado_gestion"),
        CheckConstraint("correlative_number > 0", name="ck_cite_generado_numero"),
        CheckConstraint("status IN ('GENERADO', 'ANULADO')", name="ck_cite_estado"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    cite_configuracion_id = Column("cite_configuration_id", BigInteger, ForeignKey(f"{SCHEMA}.cite_configurations.id"), nullable=False)
    documento_id = Column("document_id", BigInteger, unique=True)
    gestion = Column("year", Integer, nullable=False)
    numero_correlativo = Column("correlative_number", Integer, nullable=False)
    codigo = Column("code", String(100), nullable=False, unique=True)
    tramite_id = Column("procedure_id", BigInteger)
    estado = Column("status", String(30), nullable=False, server_default=text("'GENERADO'"))
    motivo_anulacion = Column("cancellation_reason", String(500))
    generado_en = Column("generated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"))
    generado_por = Column("generated_by", String(255))
