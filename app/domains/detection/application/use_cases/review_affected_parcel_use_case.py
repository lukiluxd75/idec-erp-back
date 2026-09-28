from typing import Optional

from app.domains.detection.domain.entities.architect_review import ArchitectReview
from app.domains.detection.domain.ports.affected_parcel_review_port import AffectedParcelReviewPort

# The only two verdicts an architect can record on an affected_parcel. The
# retraining-feedback workflow was dropped (alignment wasn't reliable enough
# for it to be worth building) -- see AffectedParcelReviewPort's docstring.
ALLOWED_ACTIONS = {"confirm", "reject"}

# Fixed catalog for affected_parcel.construction_type, chosen with the
# architect team: the real-world categories a confirmed change falls into.
# Required when action == 'confirm'; stored for statistics/graphs.
ALLOWED_CONSTRUCTION_TYPES = {
    "nueva_construccion",
    "ampliacion",
    "cambio_techo",
    "muro_nuevo",
    "demolicion",
    "otro",
}


class ReviewAffectedParcelUseCase:
    """Backs the architect's confirm/reject decision on an affected_parcel.
    Confirming means classifying the real change (construction_type, from
    ALLOWED_CONSTRUCTION_TYPES); rejecting optionally records a free-text
    comment kept for audit -- why that finding was dismissed."""

    def __init__(self, repository: AffectedParcelReviewPort):
        self._repository = repository

    def execute(
        self,
        affected_parcel_id: int,
        action: str,
        comment: Optional[str] = None,
        construction_type: Optional[str] = None,
        created_by_sub: Optional[str] = None,
    ) -> ArchitectReview:
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"action must be one of {sorted(ALLOWED_ACTIONS)}, got {action!r}")
        if action == "confirm":
            if construction_type not in ALLOWED_CONSTRUCTION_TYPES:
                raise ValueError(
                    f"construction_type must be one of {sorted(ALLOWED_CONSTRUCTION_TYPES)} "
                    f"when action is 'confirm', got {construction_type!r}"
                )
        return self._repository.review(
            affected_parcel_id=affected_parcel_id,
            action=action,
            comment=comment,
            construction_type=construction_type,
            created_by_sub=created_by_sub,
        )
