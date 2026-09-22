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
from sqlalchemy.dialects.postgresql import TIMESTAMP

from app.core.database.connection import Base

SCHEMA = "plantillas_dinamicas"


class TemplateModel(Base):
    __tablename__ = "plantilla"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    codigo = Column(String(100), nullable=False, unique=True)
    area = Column(String(100), nullable=False)
    tipo_documento = Column(String(100), nullable=False)
    descripcion = Column(String(500))
    contenido_html = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, server_default=text("1"))
    activa = Column(Boolean, nullable=False, server_default=text("true"))
    creado_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    actualizado_en = Column(TIMESTAMP(timezone=True))
    creado_por = Column(String(255))
    actualizado_por = Column(String(255))


class VariableModel(Base):
    __tablename__ = "variable"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    clave = Column(String(100), nullable=False, unique=True)
    descripcion = Column(String(500))
    tipo_dato = Column(String(50), nullable=False)
    valor_predeterminado = Column(Text)
    activa = Column(Boolean, nullable=False, server_default=text("true"))
    creado_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    actualizado_en = Column(TIMESTAMP(timezone=True))


class CiteConfiguracionModel(Base):
    """One 'sigla': a unique área + tipo_documento combination, its code format
    and whether its counter resets every gestion (year)."""

    __tablename__ = "cite_configuracion"
    __table_args__ = (
        UniqueConstraint("area_codigo", "tipo_documento_codigo", name="uq_cite_configuracion"),
        CheckConstraint("longitud_numero BETWEEN 1 AND 12", name="ck_cite_configuracion_longitud"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    area_codigo = Column(String(20), nullable=False)
    tipo_documento_codigo = Column(String(20), nullable=False)
    nombre = Column(String(150), nullable=False)
    formato = Column(String(150), nullable=False)
    longitud_numero = Column(SmallInteger, nullable=False, server_default=text("5"))
    reinicia_por_gestion = Column(Boolean, nullable=False, server_default=text("true"))
    activa = Column(Boolean, nullable=False, server_default=text("true"))


class CiteCorrelativoModel(Base):
    """The actual counter: one row per (configuracion, gestion). Incremented
    under `SELECT ... FOR UPDATE` by SqlCiteRepository.generate() so concurrent
    requests never hand out the same número_correlativo."""

    __tablename__ = "cite_correlativo"
    __table_args__ = (
        CheckConstraint("gestion BETWEEN 2000 AND 9999", name="ck_cite_correlativo_gestion"),
        CheckConstraint("ultimo_numero >= 0", name="ck_cite_correlativo_numero"),
        {"schema": SCHEMA},
    )

    cite_configuracion_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.cite_configuracion.id"), primary_key=True
    )
    gestion = Column(Integer, primary_key=True)
    ultimo_numero = Column(Integer, nullable=False, server_default=text("0"))


class CiteGeneradoModel(Base):
    __tablename__ = "cite_generado"
    __table_args__ = (
        UniqueConstraint(
            "cite_configuracion_id", "gestion", "numero_correlativo", name="uq_cite_numero_por_gestion"
        ),
        CheckConstraint("gestion BETWEEN 2000 AND 9999", name="ck_cite_generado_gestion"),
        CheckConstraint("numero_correlativo > 0", name="ck_cite_generado_numero"),
        CheckConstraint("estado IN ('GENERADO', 'ANULADO')", name="ck_cite_estado"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    cite_configuracion_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.cite_configuracion.id"), nullable=False)
    documento_id = Column(BigInteger, unique=True)
    gestion = Column(Integer, nullable=False)
    numero_correlativo = Column(Integer, nullable=False)
    codigo = Column(String(100), nullable=False, unique=True)
    tramite_id = Column(BigInteger)
    estado = Column(String(30), nullable=False, server_default=text("'GENERADO'"))
    motivo_anulacion = Column(String(500))
    generado_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    generado_por = Column(String(255))
