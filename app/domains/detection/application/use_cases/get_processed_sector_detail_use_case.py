from typing import Optional

from app.domains.detection.domain.entities.processed_sector_detail import ProcessedSectorDetail
from app.domains.detection.domain.ports.sector_history_port import SectorHistoryPort


class GetProcessedSectorDetailUseCase:
    """Feeds the map popup's detail view and Historial's per-sector screen:
    every run, every finding, every architect decision and feedback."""

    def __init__(self, repository: SectorHistoryPort):
        self._repository = repository

    def execute(self, processed_sector_id: int) -> Optional[ProcessedSectorDetail]:
        return self._repository.get_detail(processed_sector_id)
