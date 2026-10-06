from typing import List, Optional

from app.domains.detection.domain.entities.affected_parcel_report_row import AffectedParcelReportRow
from app.domains.detection.domain.ports.processed_sector_repository_port import (
    ProcessedSectorRepositoryPort,
)


class ExportCampaignReportUseCase:
    """Backs the "Exportar" button on the detection map -- by default scoped
    to the campaign currently selected in the UI (or unassigned sectors when
    none is). The export modal also lets the architect pick a *different*
    campaign than the one active on the map, or `all_campaigns=True` to list
    every confirmed/rejected parcel across every campaign at once (each row
    still carries its own campaign_code, so the report shows which campaign
    each sector/detection belongs to -- an audit view, not a cross-campaign
    rollup, so it doesn't revive the "never mix year comparisons" concern
    the single-campaign scoping was originally about)."""

    def __init__(self, repository: ProcessedSectorRepositoryPort):
        self._repository = repository

    def execute(
        self, campaign_id: Optional[int], unassigned_only: bool, all_campaigns: bool = False
    ) -> List[AffectedParcelReportRow]:
        return self._repository.list_report_rows(
            campaign_id=campaign_id, unassigned_only=unassigned_only, all_campaigns=all_campaigns
        )
