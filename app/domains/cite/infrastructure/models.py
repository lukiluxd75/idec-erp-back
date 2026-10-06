"""
ORM models para el dominio CITE.
Mapeados 1-a-1 con el esquema MySQL/MariaDB especificado.

NOTA sobre codigo_cite_completo:
  MySQL genera esta columna como STORED GENERATED (CONCAT(prefijo, '-', LPAD(correlativo,3,'0'))).
  SQLAlchemy no la escribe en INSERT/UPDATE; al leer la fila MySQL ya devuelve el valor calculado.
  Se define como `Computed` con `persisted=True` para que create_all() la declare correctamente
  y para que el mapper la incluya al leer resultados, sin intentar escribirla nunca
  (de lo contrario se dispara el error 3102 de MySQL).
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
from sqlalchemy.orm import relationship

from app.core.database.connection import Base


class GestionModel(Base):
    __tablename__ = "gestion"

    id_gestion = Column(Integer, primary_key=True, autoincrement=True)
    anio = Column(Integer, nullable=False, unique=True)
    fecha_inicial = Column(Date, nullable=False)
    fecha_final = Column(Date, nullable=False)
    activa = Column(Boolean, default=True, nullable=False)

    configuraciones = relationship("ConfiguracionCiteModel", back_populates="gestion")


class AreaModel(Base):
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


class ConfiguracionCiteModel(Base):
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


class DocumentoCiteModel(Base):
    __tablename__ = "documento_cite"
    __table_args__ = (
        UniqueConstraint("id_configuracion", "correlativo", name="uq_documento_configuracion_correlativo"),
    )

    id_documento = Column(Integer, primary_key=True, autoincrement=True)
    id_configuracion = Column(Integer, ForeignKey("configuracion_cite.id_configuracion"), nullable=False)

    # Ambas columnas se escriben explícitamente en INSERT (prefijo como denormalización
    # intencional; correlativo como valor calculado por la app dentro de la transacción).
    prefijo = Column(String(20), nullable=False)
    correlativo = Column(Integer, nullable=False)

    # Columna GENERATED STORED en MySQL: SQLAlchemy la lee pero NUNCA la escribe.
    # `Computed(..., persisted=True)` + no incluirla en inserts = workaround exacto
    # para el error 3102 "The value specified for generated column ... is not allowed."
    codigo_cite_completo = Column(
        String(50),
        Computed("CONCAT(prefijo, '-', LPAD(correlativo, 3, '0'))", persisted=True),
        nullable=False,
    )

    fecha_generacion = Column(DateTime, nullable=False)
    referencia = Column(Text, nullable=False)
    id_funcionario_remitente = Column(Integer, nullable=False)

    configuracion = relationship("ConfiguracionCiteModel", back_populates="documentos")
