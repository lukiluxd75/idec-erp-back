from typing import List, Optional

from app.domains.detection.domain.entities.processed_sector_map_item import ProcessedSectorMapItem
from app.domains.detection.domain.ports.sector_history_port import SectorHistoryPort


class ListProcessedSectorsUseCase:
    """Feeds the green-polygon map overlay in "Mapa y detección" and
    "Historial"."""

    def __init__(self, repository: SectorHistoryPort):
        self._repository = repository

    def execute(self, campaign_id: Optional[int] = None) -> List[ProcessedSectorMapItem]:
        return self._repository.list_map_items(campaign_id=campaign_id)
