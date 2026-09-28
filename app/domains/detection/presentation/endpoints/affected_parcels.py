from fastapi import APIRouter, Depends, HTTPException

from app.domains.detection.application.use_cases import ReviewAffectedParcelUseCase
from app.domains.detection.presentation.deps import get_review_affected_parcel_use_case
from app.domains.detection.presentation.schemas.detection_schema import (
    ArchitectReviewSummary,
    ReviewAffectedParcelRequest,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Detección de construcciones — validación de predios"])


@router.post("/affected-parcels/{affected_parcel_id}/review", response_model=ArchitectReviewSummary)
def review_affected_parcel(
    affected_parcel_id: int,
    payload: ReviewAffectedParcelRequest,
    use_case: ReviewAffectedParcelUseCase = Depends(get_review_affected_parcel_use_case),
    _user: UserProfile = Depends(require_permission("detection.edit")),
):
    """Architect's confirm/reject verdict on a detected parcel change.
    Confirming requires `construction_type`; rejecting accepts an optional
    audit `comment`."""
    try:
        return use_case.execute(
            affected_parcel_id=affected_parcel_id,
            action=payload.action,
            comment=payload.comment,
            construction_type=payload.construction_type,
            created_by_sub=_user.sub,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
