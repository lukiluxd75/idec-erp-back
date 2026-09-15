"""
Modelo ORM de las capturas mandadas desde la app móvil (geoextract móvil: solo saca
la foto y la manda — el resto del flujo sigue siendo de la web). Tabla nueva, dueña
de este dominio (a diferencia de resoluciones/infrastructure/models.py, que describe
un esquema externo ya existente) — se registra en `init_db_tables` para que
`Base.metadata.create_all()` la cree, mismo criterio que las tablas nuevas de
deteccionconstrucciones (campania/area_trabajo, ver CLAUDE.md §6).

Vive en el schema `public` (no uno propio de dominio) porque hoy TODA la base real
del ERP vive ahí — ver la nota de CLAUDE.md §6 sobre esa deuda técnica — no tiene
sentido que esta sea la única tabla en un schema separado.

Sin soft delete ni fecha_actualizacion: no es un registro de negocio con relevancia
legal (CLAUDE.md §6 solo pide eso para ese tipo de tablas), es un paso intermedio
que se borra al consumirse o se purga solo por TTL (ver SqlCapturaStore).
"""
from sqlalchemy import Column, DateTime, LargeBinary, String, Index

from app.core.database.connection import Base


class CapturaModel(Base):
    __tablename__ = "geoextraccion_capturas"

    id_captura = Column(String(36), primary_key=True)
    user_sub = Column(String(64), nullable=False)
    mime = Column(String(40), nullable=False)
    imagen = Column(LargeBinary, nullable=False)
    fecha_creacion = Column(DateTime, nullable=False)

    __table_args__ = (Index("ix_geoextraccion_capturas_user_sub", "user_sub"),)
