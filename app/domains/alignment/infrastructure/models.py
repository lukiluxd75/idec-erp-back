"""
ORM models mirroring the real PostgreSQL schema `alignment_results` (v1, see
doc/alignment_schema.sql) — created by this backend's own migration, same
situation as `detection/infrastructure/models.py`: this file describes the
schema, it does not own it. If these tables change, update this file to
match, never the other way around. Not registered in `init_db_tables` and
never touched by `create_all()` for the same reason.

Geometry columns use GeoAlchemy2, same as `detection`. This domain is
independent of `detection`: no shared tables, no cross-domain imports.
"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from app.core.database.connection import Base

SCHEMA = "alignment_results"

# created_by/confirmed_by reference public.users(id) at the DB level (real FK
# in the DDL) but are plain UUID columns here, not SQLAlchemy ForeignKey()s --
# same reasoning as detection/infrastructure/models.py's header: declaring the
# FK would require importing security's ORM models into this Base.metadata,
# the cross-domain coupling this backend avoids everywhere.


class AlignmentBlockModel(Base):
    __tablename__ = "alignment_block"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    year = Column(Integer, nullable=False)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)
    status = Column(String(20), nullable=False, server_default=text("'draft'"))
    transform_method = Column(String(20), nullable=False, server_default=text("'affine'"))
    transform_params = Column(JSONB)
    rmse_m = Column(Numeric(6, 2))
    cropped_image_path = Column(Text)
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
    confirmed_by = Column(UUID(as_uuid=True))
    confirmed_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, server_default=text("now()"))
    deleted_at = Column(DateTime)

    control_points = relationship(
        "AlignmentControlPointModel", back_populates="block", cascade="all, delete-orphan",
        order_by="AlignmentControlPointModel.order_index",
    )


class AlignmentControlPointModel(Base):
    __tablename__ = "alignment_control_point"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    alignment_block_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.alignment_block.id", ondelete="CASCADE"), nullable=False
    )
    order_index = Column(SmallInteger, nullable=False)
    lon_ref = Column(Numeric, nullable=False)
    lat_ref = Column(Numeric, nullable=False)
    lon_mov = Column(Numeric, nullable=False)
    lat_mov = Column(Numeric, nullable=False)

    block = relationship("AlignmentBlockModel", back_populates="control_points")
