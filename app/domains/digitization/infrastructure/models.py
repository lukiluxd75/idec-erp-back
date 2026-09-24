"""
ORM model for the digitization queue. The domain owns its `digitization` schema
outright and creates it itself at startup (see create_schema_and_tables).

Uses its own declarative base instead of core's `Base` on purpose: core's
init_db_tables runs create_all() over `Base` before this domain's startup, and
it would fail (rolling back every other table) if it saw this table before the
schema exists.
"""
from sqlalchemy import Column, DateTime, Index, Integer, LargeBinary, MetaData, String, Text, func, text
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
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_digitization_jobs_status_created_at", "status", "created_at"),
        Index("ix_digitization_jobs_requested_by", "requested_by"),
    )


def create_schema_and_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(CreateSchema(SCHEMA, if_not_exists=True))
    DigitizationBase.metadata.create_all(bind=engine)
