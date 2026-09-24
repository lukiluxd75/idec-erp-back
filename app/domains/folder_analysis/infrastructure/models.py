"""
ORM models of the folder analysis domain, schema `folder_analysis`, owned entirely
by this domain and created at its startup (presentation/router.py). Own declarative
base, same reason as digitization: core's create_all() would otherwise see these
tables before the schema exists.

`document_pages.job_id` points to a digitization job but has no foreign key: that
table lives in another domain's schema (CLAUDE.md §2).
"""
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, deferred, relationship
from sqlalchemy.schema import CreateSchema

SCHEMA = "folder_analysis"

FolderAnalysisBase = declarative_base(metadata=MetaData(schema=SCHEMA))


def _timestamps():
    return (
        Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )


class CaptureModel(FolderAnalysisBase):
    __tablename__ = "captures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_sub = Column(String(64), nullable=False)
    file_name = Column(String(255), nullable=False)
    mime = Column(String(40), nullable=False)
    image = deferred(Column(LargeBinary, nullable=False))
    thumbnail = deferred(Column(LargeBinary, nullable=False))
    status = Column(String(20), nullable=False)
    created_at, updated_at = _timestamps()

    __table_args__ = (Index("ix_folder_analysis_captures_user_status", "user_sub", "status", "created_at"),)


class DocumentModel(FolderAnalysisBase):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_sub = Column(String(64), nullable=False)
    doc_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)
    extracted_data = deferred(Column(JSONB))
    reviewed_data = deferred(Column(JSONB))
    error = Column(Text)
    analyzed_at = Column(DateTime(timezone=True))
    reviewed_at = Column(DateTime(timezone=True))
    created_at, updated_at = _timestamps()

    pages = relationship(
        "DocumentPageModel",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentPageModel.page_index",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_folder_analysis_documents_user_type", "user_sub", "doc_type", "created_at"),)


class DocumentPageModel(FolderAnalysisBase):
    __tablename__ = "document_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False)
    capture_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.captures.id"), nullable=False, unique=True)
    page_index = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    job_id = Column(String(36))
    result = Column(JSONB)
    error = Column(Text)
    created_at, updated_at = _timestamps()

    document = relationship("DocumentModel", back_populates="pages")

    __table_args__ = (UniqueConstraint("document_id", "page_index"),)


def create_schema_and_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(CreateSchema(SCHEMA, if_not_exists=True))
    FolderAnalysisBase.metadata.create_all(bind=engine)
