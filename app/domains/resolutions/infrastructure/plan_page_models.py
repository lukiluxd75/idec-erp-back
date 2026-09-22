"""ORM model for `resolutions.resolution_plan_pages` — UNLIKE
`infrastructure/models.py` (which only mirrors the mobile-owned
`resolutions`/`resolution_pages` tables and must never create them, see its
own docstring), this table is new functionality introduced by the ERP itself
(floor-plan photos for working out colindancias, added 2026-09) and this
backend DOES own and create it — see its explicit import in
app.core.database.connection.init_db_tables. It lives in the same `resolutions`
Postgres schema (already created externally) for locality with the rest of
the domain's data, with a plain string `resolution_id` (no DB-level FK) so
`create_all()` never needs to know about the mobile-owned table.
"""
from sqlalchemy import Column, DateTime, Integer, LargeBinary, String, text

from app.core.database.connection import Base


class ResolutionPlanPageModel(Base):
    __tablename__ = "resolution_plan_pages"
    __table_args__ = {"schema": "resolutions"}

    plan_page_id = Column(String(36), primary_key=True)
    resolution_id = Column(String(36), nullable=False, index=True)
    order_index = Column(Integer, nullable=False)
    planta = Column(String(60), nullable=False)
    mime = Column(String(40), nullable=False)
    file_name = Column(String)
    image = Column(LargeBinary, nullable=False)
    # 'app' (celular) o 'web' -- ver AddPlanPagesUseCase; ambos canales usan
    # el mismo endpoint, esto es solo metadata de origen.
    source = Column(String(10), nullable=False, server_default=text("'app'"))
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
