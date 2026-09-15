"""
ORM model for captures sent from the mobile app (mobile geoextract: only takes
the photo and sends it — the rest of the flow stays on the web). New table owned
by this domain (unlike resolutions/infrastructure/models.py, which describes an
external schema that already exists) — registered in `init_db_tables` so
`Base.metadata.create_all()` creates it, same criterion as new tables in
construction detection (campaign/work_area, see CLAUDE.md §6).

Lives in the `public` schema (not a domain-owned one) because today the entire
real ERP database lives there — see the CLAUDE.md §6 note on that technical debt —
no point making this the only table in a separate schema.

No soft delete or fecha_actualizacion: not a business record with legal relevance
(CLAUDE.md §6 only requires that for those tables); it is an intermediate step
deleted on consume or purged by TTL (see SqlCaptureStore).

Physical table/column names stay Spanish so existing data keeps working.
"""
from sqlalchemy import Column, DateTime, LargeBinary, String, Index

from app.core.database.connection import Base


class CaptureModel(Base):
    __tablename__ = "geoextraccion_capturas"

    id_captura = Column(String(36), primary_key=True)
    user_sub = Column(String(64), nullable=False)
    mime = Column(String(40), nullable=False)
    imagen = Column(LargeBinary, nullable=False)
    fecha_creacion = Column(DateTime, nullable=False)

    __table_args__ = (Index("ix_geoextraccion_capturas_user_sub", "user_sub"),)
