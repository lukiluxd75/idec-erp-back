from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.domains.detection.application.use_cases import (
    GetProcessedSectorDetailUseCase,
    ListProcessedSectorsUseCase,
)
from app.domains.detection.presentation.deps import (
    get_list_processed_sectors_use_case,
    get_processed_sector_detail_use_case,
)
from app.domains.detection.presentation.schemas.sector_history_schema import (
    ProcessedSectorDetail,
    ProcessedSectorMapItem,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Detección de construcciones — historial"])


@router.get("/sectors", response_model=List[ProcessedSectorMapItem])
def list_processed_sectors(
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    use_case: ListProcessedSectorsUseCase = Depends(get_list_processed_sectors_use_case),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Every processed sector's polygon + summary, for the map overlay in
    "Mapa y detección" and "Historial". `unassigned_only` (ignored if
    `campaign_id` is set) backs "Mapa y detección"'s "Sin campaña" filter --
    sectors with no campaign at all, not "no filter"."""
    return use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only)


@router.get("/sectors/{processed_sector_id}", response_model=ProcessedSectorDetail)
def get_processed_sector_detail(
    processed_sector_id: int,
    use_case: GetProcessedSectorDetailUseCase = Depends(get_processed_sector_detail_use_case),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Full history for one sector -- every run, finding, architect decision
    and feedback. Backs the map popup and Historial's detail view."""
    detail = use_case.execute(processed_sector_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Sector no encontrado.")
    return detail
