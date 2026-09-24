"""
ORM models for the `folios` domain -- schema `folios`, owned entirely by this
domain (created in init_db_tables, same as `chatbot`). No foreign key into
another domain's schema: the owner is `user_sub` (Keycloak `sub`), same
convention as resolutions/chatbot.

Ids are app-generated UUID strings (not gen_random_uuid()) so the same models
run on the SQLite test database.

Page images live in the row (LargeBinary), like geoextraction_captures and the
resolutions pages: a folio is 1-5 photos of ~0.5-1 MB. The heavy columns are
`deferred` so listing folios never pulls image bytes.
"""
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import deferred, relationship

from app.core.database.connection import Base

SCHEMA = "folios"


class FolioModel(Base):
    __tablename__ = "folios"
    __table_args__ = (
        Index("ix_folios_user_sub_created_at", "user_sub", "created_at"),
        {"schema": SCHEMA},
    )

    id = Column(String(36), primary_key=True)
    user_sub = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False)
    # Denormalized from the extracted/reviewed data for the list view.
    matricula = Column(String(40))
    page_count = Column(Integer, nullable=False)
    extracted_data = deferred(Column(JSON))
    reviewed_data = deferred(Column(JSON))
    # How the pipeline filled each field (see ProcessFolioUseCase._assemble) --
    # only downloaded on demand from the web, to debug a wrong fill.
    fill_log = deferred(Column(JSON))
    error_message = Column(Text)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    processed_at = Column(DateTime)
    confirmed_at = Column(DateTime)
    confirmed_by_sub = Column(String(64))
    deleted_at = Column(DateTime)

    pages = relationship(
        "FolioPageModel",
        back_populates="folio",
        cascade="all, delete-orphan",
        order_by="FolioPageModel.page_index",
    )


class FolioPageModel(Base):
    __tablename__ = "folio_pages"
    __table_args__ = (UniqueConstraint("folio_id", "page_index"), {"schema": SCHEMA})

    id = Column(String(36), primary_key=True)
    folio_id = Column(String(36), ForeignKey(f"{SCHEMA}.folios.id", ondelete="CASCADE"), nullable=False)
    page_index = Column(Integer, nullable=False)  # upload order, 0-based
    mime = Column(String(40), nullable=False)
    image = deferred(Column(LargeBinary, nullable=False))
    # Rotated/deskewed copy the pipeline cropped from (what the web shows).
    upright_image = deferred(Column(LargeBinary))
    rotation_deg = Column(Float)
    detected_page_number = Column(Integer)  # 'Pag X de N' read on the page
    diagnostics = deferred(Column(JSON))
    created_at = Column(DateTime, nullable=False)

    folio = relationship("FolioModel", back_populates="pages")
