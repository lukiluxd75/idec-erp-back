from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.domains.detection.application.use_cases import GetDetectionReportStatsUseCase
from app.domains.detection.presentation.deps import get_detection_report_stats_use_case
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Detección de construcciones — reportes"])


@router.get("/reports/stats")
def get_report_stats(
    campaign_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    use_case: GetDetectionReportStatsUseCase = Depends(get_detection_report_stats_use_case),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Backs the "Reportes" tab's charts -- see
    SectorHistoryPort.get_report_stats for the exact bundle shape."""
    return use_case.execute(campaign_id=campaign_id, date_from=date_from, date_to=date_to)
