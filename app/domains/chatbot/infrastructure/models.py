"""
ORM models for the `chatbot` domain — schema `chatbot`, owned entirely by this
domain (unlike `resolutions`, whose schema is owned by the mobile-app team). This
file is the source of truth: `esquema_chatbot.sql` (repo root) is generated from
it, not written by hand — see that file's header, same convention as
esquema_resoluciones.sql.

Cross-domain rule (CLAUDE.md §2): no table here has a foreign key into another
domain's schema, not even `security.users`. A user is referenced by `user_sub`
(the Keycloak token `sub`), a plain denormalized string column — the same
convention `resolutions.resolutions.user_sub` already uses for the same reason.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.core.database.connection import Base

SCHEMA = "chatbot"


def _uuid_pk() -> Column:
    return Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _created_at_column() -> Column:
    return Column(DateTime, nullable=False, server_default=text("now()"))


def _updated_at_column() -> Column:
    return Column(DateTime, nullable=False, server_default=text("now()"))


class ProcedureModel(Base):
    """A municipal `trámite` (procedure). `search_description` and `cost_note` are
    free text (the source data is narrative, not structured amounts — see
    scripts/seed_chatbot_procedures.py); `amount`/`currency` stay nullable for
    procedures where a clean numeric cost is entered later from the admin panel."""

    __tablename__ = "procedures"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    code = Column(String(100), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    search_description = Column(Text)
    cost_note = Column(Text)
    amount = Column(Numeric(10, 2))
    currency = Column(String(10), server_default=text("'Bs.'"))
    min_days = Column(Integer)
    max_days = Column(Integer)
    category = Column(String(100))
    legal_basis = Column(Text)
    location = Column(String(255))
    schedule = Column(String(255))
    requires_inspection = Column(Boolean, nullable=False, server_default=text("false"))
    requires_appointment = Column(Boolean, nullable=False, server_default=text("false"))
    deliverable = Column(String(255))
    qr_image = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    aliases = relationship("ProcedureAliasModel", back_populates="procedure", cascade="all, delete-orphan")
    requirements = relationship(
        "ProcedureRequirementModel",
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="ProcedureRequirementModel.display_order",
    )
    steps = relationship(
        "ProcedureStepModel",
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="ProcedureStepModel.step_number",
    )
    exceptions = relationship("ProcedureExceptionModel", back_populates="procedure", cascade="all, delete-orphan")
    embeddings = relationship("ProcedureEmbeddingModel", back_populates="procedure", cascade="all, delete-orphan")


class ProcedureAliasModel(Base):
    """Alternate name a citizen might use to refer to a procedure (e.g. 'visación
    de planos' for 'Visado de Plano') — extra retrieval signal on top of the name."""

    __tablename__ = "procedure_aliases"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    procedure_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.procedures.id", ondelete="CASCADE"), nullable=False
    )
    alias = Column(String(255), nullable=False)
    created_at = _created_at_column()

    procedure = relationship("ProcedureModel", back_populates="aliases")


class ProcedureRequirementModel(Base):
    __tablename__ = "procedure_requirements"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    procedure_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.procedures.id", ondelete="CASCADE"), nullable=False
    )
    description = Column(Text, nullable=False)
    detail = Column(Text)
    display_order = Column(Integer, nullable=False, server_default=text("0"))
    is_mandatory = Column(Boolean, nullable=False, server_default=text("true"))
    requirement_type = Column(String(50), server_default=text("'documento'"))
    where_to_obtain = Column(String(255))
    validity = Column(String(100))
    estimated_cost = Column(String(100))
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    procedure = relationship("ProcedureModel", back_populates="requirements")


class ProcedureStepModel(Base):
    __tablename__ = "procedure_steps"
    __table_args__ = (UniqueConstraint("procedure_id", "step_number"), {"schema": SCHEMA})

    id = _uuid_pk()
    procedure_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.procedures.id", ondelete="CASCADE"), nullable=False
    )
    step_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    location = Column(String(255))
    estimated_duration = Column(String(100))
    note = Column(Text)
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    procedure = relationship("ProcedureModel", back_populates="steps")


class ProcedureExceptionModel(Base):
    """A special case that changes what a procedure requires (e.g. inheritance
    with multiple heirs) — see prompt_builder's '## [CONTEXTO DEL TRÁMITE]' block."""

    __tablename__ = "procedure_exceptions"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    procedure_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.procedures.id", ondelete="CASCADE"), nullable=False
    )
    case_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    additional_requirements = Column(Text)
    note = Column(Text)
    created_at = _created_at_column()
    updated_at = _updated_at_column()

    procedure = relationship("ProcedureModel", back_populates="exceptions")


class FaqModel(Base):
    __tablename__ = "faqs"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    procedure_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.procedures.id", ondelete="SET NULL")
    )
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String(100), server_default=text("'general'"))
    keywords = Column(Text)
    display_order = Column(Integer, server_default=text("0"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = _created_at_column()
    updated_at = _updated_at_column()


class InstitutionalContextModel(Base):
    """General GAMC info injected into every chat prompt (contact numbers,
    schedule, etc.) — not tied to a specific procedure."""

    __tablename__ = "institutional_contexts"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    code = Column(String(100), nullable=False, unique=True)
    category = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    display_order = Column(Integer, server_default=text("0"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = _created_at_column()
    updated_at = _updated_at_column()


class ChatMessageModel(Base):
    """One turn of a conversation. `conversation_id` is server-issued (see
    AnswerQuestionUseCase) — unlike the ported prototype, the client never
    supplies its own session id or replays history; the backend reconstructs it
    from here, filtered by conversation_id AND user_sub."""

    __tablename__ = "chat_messages"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    conversation_id = Column(UUID(as_uuid=True), nullable=False)
    user_sub = Column(String(64), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    detected_procedure_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.procedures.id", ondelete="SET NULL")
    )
    match_score = Column(Numeric(5, 4))
    is_unanswered = Column(Boolean, nullable=False, server_default=text("false"))
    feedback = Column(String(20))
    feedback_comment = Column(Text)
    created_at = _created_at_column()


class ProcedureEmbeddingModel(Base):
    """Replaces the prototype's ChromaDB index: one row per embedded text
    (procedure name / alias / search_description). Similarity is computed in
    Python over these rows (see domain/services/similarity.py) — the table is
    small enough (~300 rows) that no vector extension is needed. Recomputed in
    the same transaction as any write to the procedure it belongs to, which is
    what the prototype's lazy/never-invalidated Chroma index did not do."""

    __tablename__ = "procedure_embeddings"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    procedure_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.procedures.id", ondelete="CASCADE"), nullable=False
    )
    source_kind = Column(String(20), nullable=False)
    source_text = Column(Text, nullable=False)
    model = Column(String(100), nullable=False)
    vector = Column(JSON, nullable=False)
    created_at = _created_at_column()

    procedure = relationship("ProcedureModel", back_populates="embeddings")


class ChatbotAuditModel(Base):
    """Audit trail for administrative writes on this domain's own data (CLAUDE.md
    §9) — deliberately separate from security.access_audits/geoocr_audits: those
    belong to the `security` domain's schema and writing to them from here would
    cross the domain boundary (CLAUDE.md §2). Same pattern as
    SqlRbacAdminRepository._audit: written by the infrastructure layer, its own
    commit, actor identified by user_sub (no FK into security.users)."""

    __tablename__ = "chatbot_audits"
    __table_args__ = {"schema": SCHEMA}

    id = _uuid_pk()
    actor_user_sub = Column(String(64), nullable=False)
    action = Column(String(50), nullable=False)
    description = Column(String(255))
    created_at = _created_at_column()
