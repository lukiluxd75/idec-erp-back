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
    text,
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


class ReviewedFolioModel(FolderAnalysisBase):
    __tablename__ = "reviewed_folios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_sub = Column(String(64), nullable=False)
    registration_number = Column(Text)
    registration_status = Column(Text)
    administrative_location = Column(Text)
    cadastre = Column(Text)
    property_type = Column(Text)
    location = Column(Text)
    designation = Column(Text)
    surface = Column(Text)
    measures = Column(Text)
    boundaries = Column(JSONB, nullable=False, default=dict)
    property_description = Column(Text)
    prior_title = Column(Text)
    document_date = Column(Text)
    page_number = Column(Integer)
    page_total = Column(Integer)
    ownership_entries = Column(JSONB, nullable=False, default=list)
    reviewed_data = Column(JSONB, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at, updated_at = _timestamps()


class ReviewedTaxReceiptModel(FolderAnalysisBase):
    __tablename__ = "reviewed_tax_receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_sub = Column(String(64), nullable=False)
    receipt_type = Column(Text)
    receipt_number = Column(Text)
    municipality = Column(Text)
    paid_at = Column(Text)
    collecting_entity = Column(Text)
    correspondent = Column(Text)
    branch = Column(Text)
    agency = Column(Text)
    cashier = Column(Text)
    folio = Column(Text)
    concept = Column(Text)
    tax_year = Column(Integer)
    taxpayer_type = Column(Text)
    taxpayer_id_number = Column(Text)
    taxpayer_name = Column(Text)
    property_number = Column(Text)
    cadastral_code = Column(Text)
    property_class = Column(Text)
    ownership_type = Column(Text)
    location = Column(Text)
    land_area = Column(Text)
    built_area = Column(Text)
    age_factor = Column(Text)
    ufv = Column(Text)
    taxable_base = Column(Text)
    assessed_tax = Column(Text)
    exemption = Column(Text)
    discount_10 = Column(Text)
    discount_app_5 = Column(Text)
    amount_due = Column(Text)
    amount_paid = Column(Text)
    balance = Column(Text)
    reviewed_data = Column(JSONB, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at, updated_at = _timestamps()


class ReviewedPlanModel(FolderAnalysisBase):
    __tablename__ = "reviewed_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_sub = Column(String(64), nullable=False)
    plan_name = Column(Text)
    plan_type = Column(Text)
    address = Column(Text)
    cadastral_code = Column(Text)
    scale = Column(Text)
    plan_date = Column(Text)
    extracted_data = Column(JSONB, nullable=False, default=dict)
    reviewed_data = Column(JSONB, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at, updated_at = _timestamps()


class RegisteredFolderModel(FolderAnalysisBase):
    """A project's folder. The unique index is on `lower(name)` so the list never
    shows two carpetas the architect cannot tell apart."""

    __tablename__ = "registered_folders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_sub = Column(String(64), nullable=False)
    name = Column(String(120), nullable=False)
    notes = Column(Text)
    created_at, updated_at = _timestamps()

    items = relationship(
        "RegisteredFolderItemModel",
        back_populates="folder",
        cascade="all, delete-orphan",
        order_by="RegisteredFolderItemModel.position",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "uq_folder_analysis_registered_folders_user_name",
            "user_sub",
            text("lower(name)"),
            unique=True,
        ),
        Index("ix_folder_analysis_registered_folders_user", "user_sub", "name"),
    )


class RegisteredFolderItemModel(FolderAnalysisBase):
    """One reviewed document filed in a carpeta. `document_id` is unique across
    the table, not only inside the carpeta: a document is filed once, the way the
    paper it came from sits in a single folder. Deleting the document (which
    returns its photos to the inbox) takes its row with it."""

    __tablename__ = "registered_folder_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    folder_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.registered_folders.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    position = Column(Integer, nullable=False)
    created_at, updated_at = _timestamps()

    folder = relationship("RegisteredFolderModel", back_populates="items")

    __table_args__ = (UniqueConstraint("folder_id", "position"),)


def create_schema_and_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(CreateSchema(SCHEMA, if_not_exists=True))
    FolderAnalysisBase.metadata.create_all(bind=engine)
