"""
ORM models mirroring the real PostgreSQL schema `detection_results` (schema v5,
see doc/bdd.sql) — created ahead of the backend by the DB team, same situation
as `resolutions/infrastructure/models.py`: this file describes the schema, it
does not own it. If these tables change, update this file to match, never the
other way around. Not registered in `init_db_tables` and never touched by
`create_all()` for the same reason.

Geometry columns use GeoAlchemy2 (the only place in this backend that maps a
PostGIS column through the ORM rather than handling geometry at the file level,
see `geoextraction`, which never maps a geometry column directly).

12 of the schema's 13 tables are described here -- `model_feedback` is
deliberately NOT mapped: it backed a model-retraining-feedback workflow
(chips + reasons) that was dropped (alignment wasn't reliable enough for the
chips to be worth generating). See ArchitectReviewModel's own docstring.
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from app.core.database.connection import Base

SCHEMA = "detection_results"

# `created_by`/`updated_by`/`validated_by` were migrated from BIGINT to UUID
# with a real FK to `public.users(id)` (2026-09-17, see
# scripts/migrate_detection_results_created_by_to_uuid.sql) so this domain can
# record which authenticated user did what, resolved from the Keycloak `sub`
# on the JWT -- see SqlProcessedSectorRepository._resolve_user_id.
#
# No `ForeignKey()` declared on these columns even though the constraint is
# real in Postgres: SQLAlchemy's declarative FK resolution needs the target
# Table already registered in this same `Base.metadata`, which would mean
# importing `security.infrastructure.models` here — the cross-domain ORM
# coupling this backend avoids everywhere else (see `resolutions`/`chatbot`,
# which denormalize `user_sub` instead of FKing into security's schema).


class CampaignModel(Base):
    __tablename__ = "campaign"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    period_start = Column(Date)
    period_end = Column(Date)
    status = Column(String(20), nullable=False, server_default=text("'active'"))
    n_sectors = Column(Integer, nullable=False, server_default=text("0"))
    n_affected_parcels = Column(Integer, nullable=False, server_default=text("0"))
    created_by = Column(UUID(as_uuid=True))  # references public.users(id) at the DB level, see header note
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
    closed_at = Column(DateTime)

    sectors = relationship("ProcessedSectorModel", back_populates="campaign")


class ProcessedSectorModel(Base):
    __tablename__ = "processed_sector"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    campaign_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.campaign.id"))
    name = Column(String(150))
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)
    year_a = Column(Integer, nullable=False)
    year_b = Column(Integer, nullable=False)
    status = Column(String(25), nullable=False, server_default=text("'pending'"))
    progress_pct = Column(SmallInteger, nullable=False, server_default=text("0"))
    has_changes = Column(Boolean)
    n_affected_parcels = Column(Integer, nullable=False, server_default=text("0"))
    n_new_parcels = Column(Integer, nullable=False, server_default=text("0"))
    n_removed_parcels = Column(Integer, nullable=False, server_default=text("0"))
    n_changed_parcels = Column(Integer, nullable=False, server_default=text("0"))
    created_by = Column(UUID(as_uuid=True))  # references public.users(id) at the DB level, see header note
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
    updated_by = Column(UUID(as_uuid=True))  # references public.users(id) at the DB level, see header note
    updated_at = Column(DateTime, nullable=False, server_default=text("now()"))
    processed_at = Column(DateTime)
    deleted_at = Column(DateTime)

    campaign = relationship("CampaignModel", back_populates="sectors")
    alignments = relationship(
        "AlignmentModel", back_populates="processed_sector", cascade="all, delete-orphan"
    )
    shadow_removals = relationship(
        "ShadowRemovalModel", back_populates="processed_sector", cascade="all, delete-orphan"
    )
    processing_runs = relationship(
        "ProcessingRunModel", back_populates="processed_sector", cascade="all, delete-orphan"
    )
    detections = relationship(
        "DetectionModel", back_populates="processed_sector", cascade="all, delete-orphan"
    )
    affected_parcels = relationship(
        "AffectedParcelModel", back_populates="processed_sector", cascade="all, delete-orphan"
    )
    artifacts = relationship(
        "SectorArtifactModel", back_populates="processed_sector", cascade="all, delete-orphan"
    )
    history = relationship(
        "ProcessingHistoryModel", back_populates="processed_sector", cascade="all, delete-orphan"
    )


class AlignmentModel(Base):
    __tablename__ = "alignment"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    processed_sector_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.processed_sector.id", ondelete="CASCADE"), nullable=False
    )
    method = Column(String(20), nullable=False)
    cc = Column(Numeric(5, 4))
    residual_m = Column(Numeric(6, 2))
    threshold_used = Column(Numeric(5, 4), nullable=False, server_default=text("0.75"))
    gcp_method = Column(String(20))
    base_image_source = Column(String(20))
    quality_level = Column(String(10))
    is_accepted = Column(Boolean, nullable=False, server_default=text("false"))
    warp_matrix = Column(JSONB)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))

    processed_sector = relationship("ProcessedSectorModel", back_populates="alignments")
    control_points = relationship(
        "ControlPointModel", back_populates="alignment", cascade="all, delete-orphan"
    )
    processing_runs = relationship("ProcessingRunModel", back_populates="alignment")


class ControlPointModel(Base):
    __tablename__ = "control_point"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    alignment_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.alignment.id", ondelete="CASCADE"), nullable=False
    )
    order_index = Column(SmallInteger, nullable=False)
    x_ref = Column(Numeric, nullable=False)
    y_ref = Column(Numeric, nullable=False)
    x_mov = Column(Numeric, nullable=False)
    y_mov = Column(Numeric, nullable=False)

    alignment = relationship("AlignmentModel", back_populates="control_points")


class ShadowRemovalModel(Base):
    __tablename__ = "shadow_removal"
    __table_args__ = (
        UniqueConstraint("processed_sector_id", "image"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True)
    processed_sector_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.processed_sector.id", ondelete="CASCADE"), nullable=False
    )
    image = Column(String(1), nullable=False)
    shadow_pct = Column(Numeric(5, 2))
    mask_path = Column(Text, nullable=False)
    original_path = Column(Text, nullable=False)
    deshadowed_path = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))

    processed_sector = relationship("ProcessedSectorModel", back_populates="shadow_removals")


class ProcessingRunModel(Base):
    __tablename__ = "processing_run"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    processed_sector_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.processed_sector.id", ondelete="CASCADE"), nullable=False
    )
    alignment_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.alignment.id"))
    # Holds the full request payload sent to the GPU engine PLUS its `job_id` —
    # the schema has no dedicated job_id column (see design discussion in the PR),
    # so this JSONB is the only place that correlates a run with the engine's job.
    params = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))

    processed_sector = relationship("ProcessedSectorModel", back_populates="processing_runs")
    alignment = relationship("AlignmentModel", back_populates="processing_runs")
    detections = relationship("DetectionModel", back_populates="processing_run")
    artifacts = relationship("SectorArtifactModel", back_populates="processing_run")


class DetectionModel(Base):
    __tablename__ = "detection"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    processed_sector_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.processed_sector.id", ondelete="CASCADE"), nullable=False
    )
    processing_run_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.processing_run.id"))
    type = Column(String(20), nullable=False)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)
    probability = Column(Numeric(5, 4))
    area_m2 = Column(Numeric)
    is_included_in_report = Column(Boolean, nullable=False, server_default=text("true"))
    reject_reason = Column(String(30))
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))

    processed_sector = relationship("ProcessedSectorModel", back_populates="detections")
    processing_run = relationship("ProcessingRunModel", back_populates="detections")
    affected_parcels = relationship("AffectedParcelModel", back_populates="detection")


class AffectedParcelModel(Base):
    __tablename__ = "affected_parcel"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    processed_sector_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.processed_sector.id", ondelete="CASCADE"), nullable=False
    )
    detection_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.detection.id", ondelete="SET NULL"))
    cadastral_code = Column(String(30))
    block_code = Column(String(30))
    parcel_geom = Column(Geometry("MULTIPOLYGON", srid=4326))
    match_confidence = Column(String(10))
    match_distance_m = Column(Numeric(6, 2))
    no_match_reason = Column(String(30))
    change_type = Column(String(20), nullable=False)
    construction_type = Column(String(30))
    validation_status = Column(String(20), nullable=False, server_default=text("'pending'"))
    validated_by = Column(UUID(as_uuid=True))  # references public.users(id) at the DB level, see header note
    validated_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime, nullable=False, server_default=text("now()"))
    deleted_at = Column(DateTime)

    processed_sector = relationship("ProcessedSectorModel", back_populates="affected_parcels")
    detection = relationship("DetectionModel", back_populates="affected_parcels")
    reviews = relationship(
        "ArchitectReviewModel", back_populates="affected_parcel", cascade="all, delete-orphan"
    )


class SectorArtifactModel(Base):
    __tablename__ = "sector_artifact"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    processed_sector_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.processed_sector.id", ondelete="CASCADE"), nullable=False
    )
    processing_run_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.processing_run.id"))
    kind = Column(String(30), nullable=False)
    path = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))

    processed_sector = relationship("ProcessedSectorModel", back_populates="artifacts")
    processing_run = relationship("ProcessingRunModel", back_populates="artifacts")


class ArchitectReviewModel(Base):
    """The architect's confirm/reject verdict on an affected_parcel (see
    ReviewAffectedParcelUseCase). `model_feedback` is intentionally not
    mapped here: the retraining-feedback workflow (chips, reasons) was
    dropped -- alignment wasn't reliable enough for it to be worth building.
    The `model_feedback` table still exists in the DDL (bdd.sql) but nothing
    in this backend writes to it anymore."""

    __tablename__ = "architect_review"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    affected_parcel_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.affected_parcel.id", ondelete="CASCADE"), nullable=False
    )
    action = Column(String(20), nullable=False)
    comment = Column(Text)
    created_by = Column(UUID(as_uuid=True))  # references public.users(id) at the DB level, see header note
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))

    affected_parcel = relationship("AffectedParcelModel", back_populates="reviews")


class ProcessingHistoryModel(Base):
    __tablename__ = "processing_history"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    processed_sector_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.processed_sector.id", ondelete="CASCADE"), nullable=False
    )
    stage = Column(String(20), nullable=False)
    status = Column(String(10), nullable=False)
    message = Column(Text)
    duration_seconds = Column(Numeric)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))

    processed_sector = relationship("ProcessedSectorModel", back_populates="history")


class ModuleParameterModel(Base):
    __tablename__ = "module_parameter"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    param_key = Column(String(50), nullable=False, unique=True)
    value = Column(Text, nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime, nullable=False, server_default=text("now()"))
