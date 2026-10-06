from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.domains.detection.application.use_cases import CreateCampaignUseCase, ListCampaignsUseCase
from app.domains.detection.domain.exceptions import CampaignCodeAlreadyExists
from app.domains.detection.presentation.deps import (
    get_create_campaign_use_case,
    get_list_campaigns_use_case,
)
from app.domains.detection.presentation.schemas.detection_schema import (
    CampaignCreateRequest,
    CampaignSummary,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Detección de construcciones — campañas"])


@router.get("/campaigns", response_model=List[CampaignSummary])
def list_campaigns(
    use_case: ListCampaignsUseCase = Depends(get_list_campaigns_use_case),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Active campaigns for the detection start screen's campaign picker."""
    return use_case.execute()


@router.post("/campaigns", response_model=CampaignSummary)
def create_campaign(
    payload: CampaignCreateRequest,
    use_case: CreateCampaignUseCase = Depends(get_create_campaign_use_case),
    _user: UserProfile = Depends(require_permission("detection.manage_campaigns")),
):
    """Backs the "+ Nueva campaña" quick-create on the detection start screen.
    Deliberately a stricter permission than `detection.edit` (which the
    Deteccion_Construcciones role also has) -- only Administrador holds
    `detection.manage_campaigns`, so campaign creation stays an admin-only
    action while everyone who can edit detections keeps picking from the
    campaigns that already exist."""
    try:
        return use_case.execute(**payload.model_dump(), created_by_sub=_user.sub)
    except CampaignCodeAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
