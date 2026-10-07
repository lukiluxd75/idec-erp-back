from datetime import date
from typing import Optional

from app.domains.detection.domain.ports.sector_history_port import SectorHistoryPort


class GetDetectionReportStatsUseCase:
    """Backs the "Reportes" tab's charts -- see SectorHistoryPort.get_report_stats
    for the exact bundle shape."""

    def __init__(self, repository: SectorHistoryPort):
        self._repository = repository

    def execute(
        self,
        campaign_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> dict:
        return self._repository.get_report_stats(campaign_id=campaign_id, date_from=date_from, date_to=date_to)
