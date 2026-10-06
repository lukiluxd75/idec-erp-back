from abc import ABC, abstractmethod
from typing import List, Optional

from app.domains.detection.domain.entities.processed_sector_detail import ProcessedSectorDetail
from app.domains.detection.domain.entities.processed_sector_map_item import ProcessedSectorMapItem
from app.domains.detection.domain.entities.search_result import SearchResult


class SectorHistoryPort(ABC):
    """Port the `detection` infrastructure must implement (see CLAUDE.md §3)
    for read-only browsing of what's already in `detection_results` -- the
    map overlay in "Mapa y detección"/"Historial" (green polygons + popup)
    and Historial's full detail view. Never writes anything."""

    @abstractmethod
    def list_map_items(
        self, campaign_id: Optional[int] = None, unassigned_only: bool = False
    ) -> List[ProcessedSectorMapItem]:
        """Every non-deleted processed_sector with its geometry, for the map
        overlay. `campaign_id` scopes to one campaign; `unassigned_only`
        (ignored when `campaign_id` is given) scopes to sectors with no
        campaign at all -- "Mapa y detección"'s "Sin campaña" filter, distinct
        from the unfiltered browse-everything call Historial makes with
        neither argument set."""

    @abstractmethod
    def get_detail(self, processed_sector_id: int) -> Optional[ProcessedSectorDetail]:
        """Full history for one sector: every processing_run (auto + any
        manual realignments, oldest first), each with its alignment quality
        and the parcels it found, each with its full review/feedback trail."""

    @abstractmethod
    def search(self, query: str, limit: int = 8) -> List[SearchResult]:
        """Matches `query` against a sector's id/name, a predio's
        cadastral_code, and a campaign's code/name -- up to `limit` results
        per kind (never a single combined cap, so one kind's matches can't
        crowd out another's in the dropdown). Backs the map's search box and
        Historial's lookup (see SearchResult's own docstring)."""
