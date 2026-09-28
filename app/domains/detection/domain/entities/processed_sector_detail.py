"""Read projection of a `processed_sector`'s full history -- every run
(auto + any manual re-alignments), every finding, every architect decision --
for the "Historial" tab and the map popup's detail view. No SQLAlchemy, no
FastAPI."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ReviewRecord:
    action: str
    comment: Optional[str]
    created_by_username: Optional[str]
    created_at: Optional[datetime]


@dataclass
class ParcelDetail:
    id: int
    change_type: str
    validation_status: str
    cadastral_code: Optional[str] = None
    probability: Optional[float] = None
    area_m2: Optional[float] = None
    construction_type: Optional[str] = None
    parcel_geom_geojson: Optional[Dict[str, Any]] = None
    validated_by_username: Optional[str] = None
    validated_at: Optional[datetime] = None
    reviews: List[ReviewRecord] = field(default_factory=list)


@dataclass
class RunDetail:
    id: int
    alignment_method: str
    created_at: Optional[datetime] = None
    alignment_quality_level: Optional[str] = None
    alignment_cc: Optional[float] = None
    alignment_residual_m: Optional[float] = None
    alignment_is_main: bool = False
    parcels: List[ParcelDetail] = field(default_factory=list)


@dataclass
class ProcessedSectorDetail:
    id: int
    year_a: int
    year_b: int
    status: str
    n_affected_parcels: int
    n_new_parcels: int
    n_removed_parcels: int
    n_changed_parcels: int
    name: Optional[str] = None
    campaign_code: Optional[str] = None
    campaign_name: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    runs: List[RunDetail] = field(default_factory=list)
