"""Read projection of a `processed_sector` for the map overlay (green polygon
+ popup) in "Mapa y detección" and "Historial". No SQLAlchemy, no FastAPI."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class ProcessedSectorMapItem:
    id: int
    geom_geojson: dict[str, Any]
    year_a: int
    year_b: int
    status: str
    has_changes: Optional[bool]
    n_affected_parcels: int
    n_new_parcels: int
    n_removed_parcels: int
    n_changed_parcels: int
    n_confirmed_parcels: int = 0
    n_rejected_parcels: int = 0
    n_pending_parcels: int = 0
    name: Optional[str] = None
    campaign_code: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
