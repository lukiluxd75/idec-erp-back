"""
Modelos ORM que reflejan el esquema REAL de PostgreSQL del módulo Resoluciones —
schema `resolutions`, creado por el equipo/servicio de la app móvil (la que sube las
fotos de las resoluciones escaneadas). Este archivo no define el esquema, lo describe
(mismo criterio que app/domains/seguridad/infrastructure/models.py): si esas tablas
cambian, este archivo se actualiza para reflejarlo, nunca al revés. Por eso NO se
registran en `init_db_tables` (ver core/database/connection.py) — esas tablas ya
existen y tienen datos reales cargados desde el celular, no hay nada que crear.

Cada resolución le pertenece a un usuario concreto (`user_sub`, el `sub` de su token de
Keycloak) — es lo que hace que "Mis resoluciones" en el frontend sea, literalmente, del
usuario logueado y no una lista global (ver SqlResolucionRepository, que siempre filtra
por user_sub).
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from app.core.database.connection import Base


class ResolucionModel(Base):
    __tablename__ = "resolutions"
    __table_args__ = {"schema": "resolutions"}

    resolution_id = Column(String(36), primary_key=True)
    resolution_number = Column(String(120), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False)
    user_sub = Column(String(64), nullable=False)
    table_data = Column(JSON)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime, nullable=False, server_default=text("now()"))
    deleted_at = Column(DateTime)

    paginas = relationship(
        "ResolucionPaginaModel",
        back_populates="resolucion",
        cascade="all, delete-orphan",
        order_by="ResolucionPaginaModel.order_index",
    )


class ResolucionPaginaModel(Base):
    __tablename__ = "resolution_pages"
    __table_args__ = {"schema": "resolutions"}

    page_id = Column(String(36), primary_key=True)
    resolution_id = Column(
        String(36), ForeignKey("resolutions.resolutions.resolution_id", ondelete="CASCADE"), nullable=False
    )
    order_index = Column(Integer, nullable=False)
    mime = Column(String(40), nullable=False)
    file_name = Column(String)
    image = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))

    resolucion = relationship("ResolucionModel", back_populates="paginas")
