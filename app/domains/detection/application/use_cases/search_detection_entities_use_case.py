from typing import List

from app.domains.detection.domain.entities.search_result import SearchResult
from app.domains.detection.domain.ports.sector_history_port import SectorHistoryPort


class SearchDetectionEntitiesUseCase:
    """Backs the map's search box ("Mapa y detección") and Historial's
    lookup -- one query, three kinds of matches (sector, predio, campaña).
    Built once so neither tab re-implements its own search (see
    SearchResult's docstring for what each kind means)."""

    def __init__(self, repository: SectorHistoryPort):
        self._repository = repository

    def execute(self, query: str, limit: int = 8) -> List[SearchResult]:
        return self._repository.search(query=query, limit=limit)
