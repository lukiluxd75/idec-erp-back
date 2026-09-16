from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.domains.chatbot.domain.entities.procedure import (
    Faq,
    InstitutionalContext,
    Procedure,
    ProcedureException,
    Step,
)


class ProcedureRepositoryPort(ABC):
    """Port the `chatbot` infrastructure layer must implement (CLAUDE.md §3).
    application/ only knows this interface, never SQLAlchemy or the real schema."""

    @abstractmethod
    def list_active(self) -> List[Procedure]:
        """Every active procedure with its aliases and search_description loaded
        — the full set retrieval and (re)indexing operate over."""

    @abstractmethod
    def list_for_admin(self) -> List[Procedure]:
        """Every procedure (active and inactive) for the admin catalog screen."""

    @abstractmethod
    def get_by_code(self, code: str) -> Optional[Procedure]:
        """Full detail (requirements, steps, exceptions, faqs) of one procedure."""

    @abstractmethod
    def get_by_id(self, procedure_id: str) -> Optional[Procedure]:
        """Full detail of one procedure by internal id (used once a match is found)."""

    @abstractmethod
    def update_admin_fields(
        self,
        code: str,
        name: str,
        description: Optional[str],
        amount: Optional[float],
        currency: Optional[str],
        is_active: bool,
        actor_user_sub: str,
    ) -> Optional[Procedure]:
        """Editable subset from the admin panel. None if the code does not exist.
        Writes a chatbot_audits row on success (CLAUDE.md §9) — see
        SqlProcedureRepository._audit, same pattern as SqlRbacAdminRepository."""

    @abstractmethod
    def upsert_from_ingest(
        self, name: str, requirements: List[str], cost_note: str, actor_user_sub: str
    ) -> Procedure:
        """Create or update a procedure from an OCR-ingested document. Requirements
        fully replace whatever the procedure had before, same as re-ingesting.
        Also audited (see update_admin_fields)."""

    @abstractmethod
    def get_steps(self, procedure_id: str) -> List[Step]:
        pass

    @abstractmethod
    def get_exceptions(self, procedure_id: str) -> List[ProcedureException]:
        pass

    @abstractmethod
    def get_faqs(self, procedure_id: str) -> List[Faq]:
        pass

    @abstractmethod
    def get_institutional_context(self) -> List[InstitutionalContext]:
        """Active institutional-context entries, in display order."""

    @abstractmethod
    def save_embeddings(self, procedure_id: str, model: str, entries: List[Tuple[str, str, List[float]]]) -> None:
        """Replaces every embedding row of `procedure_id` with `entries`
        (source_kind, source_text, vector), in the same transaction as the write
        that triggered it. `entries` empty just clears the procedure's rows."""

    @abstractmethod
    def list_all_embeddings(self) -> List[Tuple[str, str, List[float]]]:
        """Every (procedure_id, source_text, vector) row, for similarity search."""
