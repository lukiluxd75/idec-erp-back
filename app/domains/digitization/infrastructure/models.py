"""
ORM model for the digitization queue. The domain owns its `digitization` schema
outright and creates it itself at startup (see create_schema_and_tables).

Uses its own declarative base instead of core's `Base` on purpose: core's
init_db_tables runs create_all() over `Base` before this domain's startup, and
it would fail (rolling back every other table) if it saw this table before the
schema exists.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, deferred
from sqlalchemy.schema import CreateSchema

SCHEMA = "digitization"

DigitizationBase = declarative_base(metadata=MetaData(schema=SCHEMA))


class DigitizationJobModel(DigitizationBase):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    status = Column(String(20), nullable=False)
    file_name = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    image = deferred(Column(LargeBinary, nullable=False))
    prepared_image = deferred(Column(LargeBinary, nullable=False))
    requested_by = Column(String(64), nullable=False)
    attempts = Column(Integer, nullable=False, server_default=text("0"))
    worker_host = Column(String(255), nullable=True)
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    instructions = deferred(Column(Text, nullable=True))
    output_template = deferred(Column(JSONB, nullable=True))
    source = Column(String(40), nullable=True)
    # Raised from the monitor to ask the PC running this job to drop it. Read by
    # the dispatching process, which may not be the one that got the request.
    stop_requested = Column(Boolean, nullable=False, server_default=text("false"))
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_digitization_jobs_status_created_at", "status", "created_at"),
        Index("ix_digitization_jobs_requested_by", "requested_by"),
    )


# create_all() never alters an existing table, so columns added after the first
# deploy are added here. Only safe, idempotent ADD COLUMN IF NOT EXISTS.
_ADDED_COLUMNS = {
    "jobs": (
        "instructions TEXT",
        "output_template JSONB",
        "source VARCHAR(40)",
        "stop_requested BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    "host_usage": ("stop_requested BOOLEAN NOT NULL DEFAULT FALSE",),
}


class HostUsageModel(DigitizationBase):
    """One row per in-flight call another domain (folios, chatbot) is making to an
    architect PC. Digitization's own jobs are not here -- they are already in
    `jobs`. Rows are deleted when the call ends and ignored once expired."""

    __tablename__ = "host_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    host = Column(String(255), nullable=False)
    used_by = Column(String(40), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    # Raised from the monitor to ask the borrowing domain to drop its call.
    stop_requested = Column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (Index("ix_digitization_host_usage_expires_at", "expires_at"),)


def create_schema_and_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(CreateSchema(SCHEMA, if_not_exists=True))
    DigitizationBase.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            for column in columns:
                conn.execute(text(f"ALTER TABLE {SCHEMA}.{table} ADD COLUMN IF NOT EXISTS {column}"))
