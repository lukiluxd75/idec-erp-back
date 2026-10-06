"""One match from the cross-entity search (sector / predio / campaña) that
backs the map's search box in "Mapa y detección" and the lookup in
"Historial" (see SearchDetectionEntitiesUseCase) -- built once, used by
both, so neither tab re-implements its own search. No SQLAlchemy, no
FastAPI (see CLAUDE.md §3).

`kind` discriminates which of the optional fields are populated:
- "sector": sector_id, status, geom_geojson (the sector's own polygon, to
  fitBounds on) -- PLUS the campaign_* fields below, if the sector has one.
- "parcel": sector_id (which sector it belongs to), cadastral_code,
  validation_status, geom_geojson (the PARCEL's own polygon this time, for a
  tighter fitBounds than the whole sector) -- PLUS the campaign_* fields
  below, from the parcel's own sector.
- "campaign": campaign_id, campaign_code, year_a, year_b (enough to drive
  the same campaign-switch flow the "Campaña" dropdown already uses --
  switching campaign resets the map, it doesn't fitBounds anywhere, since a
  campaign has no single polygon).

campaign_id/campaign_code/campaign_name/year_a/year_b are set on "sector"
and "parcel" results too (not just "campaign" ones): the map overlay only
renders sectors belonging to whatever campaign is currently active, so
landing on a sector/predio from a DIFFERENT campaign needs to switch to its
campaign first, or its real polygon never appears -- confirmed bug: without
this, the architect's view centers on the right spot but shows nothing
(the search's own temporary highlight clears itself after a couple of
seconds, with no durable polygon left behind)."""
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SearchResult:
    kind: str  # "sector" | "parcel" | "campaign"
    label: str
    sector_id: Optional[int] = None
    status: Optional[str] = None
    cadastral_code: Optional[str] = None
    validation_status: Optional[str] = None
    campaign_id: Optional[int] = None
    campaign_code: Optional[str] = None
    campaign_name: Optional[str] = None
    year_a: Optional[int] = None
    year_b: Optional[int] = None
    geom_geojson: Optional[dict[str, Any]] = None
