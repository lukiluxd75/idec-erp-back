from typing import List, Optional

from app.domains.detection.domain.entities.affected_parcel_report_row import AffectedParcelReportRow
from app.domains.detection.domain.ports.processed_sector_repository_port import (
    ProcessedSectorRepositoryPort,
)


class ExportCampaignReportUseCase:
    """Backs the "Exportar" button on the detection map -- always scoped to
    the campaign currently selected in the UI (or unassigned sectors when
    none is), never a global cross-campaign export (see
    ProcessedSectorRepositoryPort.list_report_rows for why)."""

    def __init__(self, repository: ProcessedSectorRepositoryPort):
        self._repository = repository

    def execute(self, campaign_id: Optional[int], unassigned_only: bool) -> List[AffectedParcelReportRow]:
        return self._repository.list_report_rows(campaign_id=campaign_id, unassigned_only=unassigned_only)
