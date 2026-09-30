from typing import Optional

from app.domains.detection.domain.entities.architect_review import ArchitectReview
from app.domains.detection.domain.ports.affected_parcel_review_port import AffectedParcelReviewPort

# The only two verdicts an architect can record on an affected_parcel. The
# retraining-feedback workflow was dropped (alignment wasn't reliable enough
# for it to be worth building) -- see AffectedParcelReviewPort's docstring.
ALLOWED_ACTIONS = {"confirm", "reject"}

# Fixed catalog offered by the frontend's dropdown for affected_parcel.
# construction_type -- the real-world categories a confirmed change usually
# falls into. Not an exhaustive whitelist: picking "Otro" there reveals a
# free-text field, and *that* short title is what actually gets sent and
# stored here instead of the literal word "otro" (see
# CONSTRUCTION_TYPE_MAX_LENGTH below) -- there is no dedicated column for it,
# it goes straight into construction_type like every other value.
ALLOWED_CONSTRUCTION_TYPES = {
    "nueva_construccion",
    "ampliacion",
    "cambio_techo",
    "muro_nuevo",
    "demolicion",
}

# Matches affected_parcel.construction_type's VARCHAR(30) -- a short title,
# not a description, whether it's one of the catalog values above or a
# custom one typed under "Otro".
CONSTRUCTION_TYPE_MAX_LENGTH = 30


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
            value = (construction_type or "").strip()
            if not value:
                raise ValueError("construction_type es obligatorio cuando action es 'confirm'.")
            if len(value) > CONSTRUCTION_TYPE_MAX_LENGTH:
                raise ValueError(
                    f"construction_type no puede superar {CONSTRUCTION_TYPE_MAX_LENGTH} caracteres."
                )
            construction_type = value
        return self._repository.review(
            affected_parcel_id=affected_parcel_id,
            action=action,
            comment=comment,
            construction_type=construction_type,
            created_by_sub=created_by_sub,
        )
