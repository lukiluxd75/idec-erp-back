"""
ORM models mirroring the REAL PostgreSQL schema for the Resolutions module —
schema `resolutions`, created by the mobile-app team/service (uploads scanned
resolution photos). This file describes the schema; it does not own it. If those
tables change, update this file to match — never the other way around. That is
why they are NOT registered in `init_db_tables` (see core/database/connection.py):
the tables already exist with real data from the phone; there is nothing to create.

Each resolution belongs to a concrete user (`user_sub`, the Keycloak token `sub`)
— that is what makes "Mis resoluciones" in the frontend literally the logged-in
user's list, not a global one (see SqlResolutionRepository, which always filters
by user_sub).

Physical column/table names in this schema are already English. Mapping notes for
legacy Spanish RBAC tables: app/core/database/LEGACY_SCHEMA_MAP.md.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from app.core.database.connection import Base


class ResolutionModel(Base):
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

    pages = relationship(
        "ResolutionPageModel",
        back_populates="resolution",
        cascade="all, delete-orphan",
        order_by="ResolutionPageModel.order_index",
    )


class ResolutionPageModel(Base):
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

    resolution = relationship("ResolutionModel", back_populates="pages")
