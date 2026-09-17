"""ORM models for the `avaluos` schema in idec_erp — created and owned by the database
team (not this app; unlike `chatbot`, this domain never runs CREATE SCHEMA/create_all,
same approach as `resolutions`). This file describes the real tables, it does not define
them: if they change, this file is updated to match, never the other way around.

avaluos.avaluos_migrados predates the ERP's English-naming policy (Guía §10.1/§12.4) —
two of its physical columns are still in Spanish (migrado_por/migrado_en); the ORM
attributes stay in English (migrated_by/migrated_at) and map explicitly via `name=`,
same EN-code/ES-physical pattern the rest of the ERP already uses. Renaming those
columns is a coordinated migration, not something to do from a feature PR.

avaluos.appraisal_observations is a new table (proposed in esquema_avaluos.sql, created
by the database team on request) — fully English, no EN/ES mapping needed.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.connection import Base


class MigratedAppraisalModel(Base):
    __tablename__ = "avaluos_migrados"
    __table_args__ = {"schema": "avaluos"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    form_number: Mapped[str] = mapped_column(String(40), nullable=False)
    operativo_appraisal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    address: Mapped[str | None] = mapped_column(Text)
    cadastral_code: Mapped[str | None] = mapped_column(String(30))
    owner_name: Mapped[str | None] = mapped_column(String(250))
    owner_document: Mapped[str | None] = mapped_column(String(40))
    land_area: Mapped[float | None] = mapped_column(Numeric(14, 2))
    blocks_area: Mapped[float | None] = mapped_column(Numeric(14, 2))
    improvements_area: Mapped[float | None] = mapped_column(Numeric(14, 2))
    total_value: Mapped[float | None] = mapped_column(Numeric(18, 2))

    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # Physical columns are still Spanish (migrado_por/migrado_en) — see module docstring.
    migrated_by: Mapped[str] = mapped_column("migrado_por", String(120), nullable=False)
    migrated_at: Mapped[datetime] = mapped_column("migrado_en", DateTime(timezone=True), server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class ObservationBatchModel(Base):
    __tablename__ = "appraisal_observations"
    __table_args__ = {"schema": "avaluos"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    form_number: Mapped[str] = mapped_column(String(40), nullable=False)
    operativo_appraisal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    observations: Mapped[list] = mapped_column(JSONB, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(120), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
