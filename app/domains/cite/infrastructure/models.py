"""
ORM models para el dominio CITE, esquema `public` de PostgreSQL.

Las tablas NO se crean desde la aplicacion: se aplican a mano con
`database/cite_postgresql.sql`. Por eso el dominio usa su propia base
declarativa en vez de la `Base` de core -- core corre create_all() sobre `Base`
al arrancar, y si viera estas tablas intentaria crearlas (y un fallo ahi
revierte la creacion de todas las demas tablas del backend).

Este archivo describe el esquema real, no lo define: si la BD cambia, se
actualiza este archivo para que coincida, nunca al reves.

NOTA sobre codigo_cite_completo:
  Es una columna GENERATED ALWAYS ... STORED en PostgreSQL:
  prefijo || '-' || lpad(correlativo::text, 3, '0').
  Se declara como `Computed(..., persisted=True)` para que SQLAlchemy la lea
  pero no la escriba nunca en INSERT/UPDATE (la BD rechaza cualquier valor
  explicito sobre una columna generada).
  El cast `::text` es obligatorio: `lpad` en PostgreSQL solo existe como
  lpad(text, integer, text) y no convierte el integer sola.
"""
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

# Base propia: ver el encabezado. Tambien deja de competir con el dominio
# security, que tiene su propia clase `AreaModel` (tabla `areas`, la del RBAC)
# sobre la base de core; al estar en registros distintos, el nombre a secas ya
# no es ambiguo en las relationships de abajo.
CiteBase = declarative_base()


class GestionModel(CiteBase):
    __tablename__ = "gestion"

    id_gestion = Column(Integer, primary_key=True, autoincrement=True)
    anio = Column(Integer, nullable=False, unique=True)
    fecha_inicial = Column(Date, nullable=False)
    fecha_final = Column(Date, nullable=False)
    activa = Column(Boolean, default=True, nullable=False)

    configuraciones = relationship("ConfiguracionCiteModel", back_populates="gestion")


class AreaModel(CiteBase):
    __tablename__ = "area"

    id_area = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    tipo = Column(
        Enum("Secretaria", "Direccion", "Jefatura", "Unidad", name="area_tipo_enum"),
        nullable=False,
    )
    id_area_padre = Column(Integer, ForeignKey("area.id_area", ondelete="SET NULL"), nullable=True)

    area_padre = relationship("AreaModel", remote_side="AreaModel.id_area")
    configuraciones = relationship("ConfiguracionCiteModel", back_populates="area")


class ConfiguracionCiteModel(CiteBase):
    __tablename__ = "configuracion_cite"
    __table_args__ = (
        UniqueConstraint("id_gestion", "prefijo", name="uq_configuracion_gestion_prefijo"),
    )

    id_configuracion = Column(Integer, primary_key=True, autoincrement=True)
    id_area = Column(Integer, ForeignKey("area.id_area"), nullable=False)
    id_gestion = Column(Integer, ForeignKey("gestion.id_gestion"), nullable=False)
    prefijo = Column(String(20), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)

    area = relationship("AreaModel", back_populates="configuraciones")
    gestion = relationship("GestionModel", back_populates="configuraciones")
    documentos = relationship("DocumentoCiteModel", back_populates="configuracion")


class DocumentoCiteModel(CiteBase):
    __tablename__ = "documento_cite"
    __table_args__ = (
        UniqueConstraint("id_configuracion", "correlativo", name="uq_documento_configuracion_correlativo"),
    )

    id_documento = Column(Integer, primary_key=True, autoincrement=True)
    id_configuracion = Column(Integer, ForeignKey("configuracion_cite.id_configuracion"), nullable=False)

    # Ambas columnas se escriben explicitamente en INSERT (prefijo como denormalizacion
    # intencional; correlativo como valor calculado por la app dentro de la transaccion).
    prefijo = Column(String(20), nullable=False)
    correlativo = Column(Integer, nullable=False)

    # Columna GENERATED ... STORED: SQLAlchemy la lee pero NUNCA la escribe (ver encabezado).
    codigo_cite_completo = Column(
        String(50),
        Computed("prefijo || '-' || lpad(correlativo::text, 3, '0')", persisted=True),
        nullable=False,
    )

    fecha_generacion = Column(DateTime, nullable=False)
    referencia = Column(Text, nullable=False)
    id_funcionario_remitente = Column(Integer, nullable=False)

    configuracion = relationship("ConfiguracionCiteModel", back_populates="documentos")
