"""Port against catastro_operativo, the external Avalúos system's own DB. Mostly read
(queue, detail); the two status-changing methods are the only writes the ERP ever makes
there, and they touch nothing but the appraisal's status_id.
"""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domains.appraisal_review.domain.entities import AppraisalDetail, AppraisalSummary


class OperativoAppraisalPort(ABC):

    @abstractmethod
    def list_pending_review(self, limit: int = 100) -> list[AppraisalSummary]:
        """Appraisals the architect sent for review (status 'submitted'), oldest first."""

    @abstractmethod
    def search_by_form_number(self, term: str, limit: int = 40) -> list[AppraisalSummary]:
        """Appraisals whose form_number contains `term` (any status) — lets the reviewer
        pull up a specific form directly instead of waiting for it to reach 'submitted'."""

    @abstractmethod
    def get_by_form_number(self, form_number: str) -> AppraisalDetail | None:
        """Full appraisal by exact form_number, or None if it doesn't exist."""

    @abstractmethod
    def mark_needs_correction(self, appraisal_id: UUID) -> None:
        """Flips the appraisal's status to 'needs_correction' after observations were sent."""

    @abstractmethod
    def mark_approved(self, appraisal_id: UUID) -> None:
        """Flips the appraisal's status to 'approved' after a clean review."""
