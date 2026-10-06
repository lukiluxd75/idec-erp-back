from abc import ABC, abstractmethod
from typing import Optional

from app.domains.detection.domain.entities.architect_review import ArchitectReview


class AffectedParcelReviewPort(ABC):
    """Port the `detection` infrastructure must implement (see CLAUDE.md §3)
    for the architect's parcel-validation screen: `architect_review` against
    an existing `affected_parcel`. Only two actions exist (see
    ReviewAffectedParcelUseCase): confirm (the architect classifies the real
    change -- new construction, roof change, new wall, ... -- see
    `construction_type`) or reject (optionally with a comment, kept for
    audit -- why that finding was dismissed).

    Every write here also re-evaluates its `processed_sector`: once none of
    its affected_parcel rows are still 'pending', the sector moves to
    'completed' -- regardless of whether the outcome was all confirmed, all
    rejected, or mixed (see _maybe_complete_sector on the SQL adapter)."""

    @abstractmethod
    def review(
        self,
        affected_parcel_id: int,
        action: str,
        comment: Optional[str] = None,
        construction_type: Optional[str] = None,
        created_by_sub: Optional[str] = None,
    ) -> ArchitectReview:
        """Record a confirm/reject decision. `construction_type` is required
        for 'confirm' (see ReviewAffectedParcelUseCase's catalog) and stored
        on affected_parcel.construction_type; `comment` is an optional
        free-text note, meaningful mostly for 'reject' (why that finding was
        dismissed) but accepted either way."""
