from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class ProcessedSectorMapItem(BaseModel):
    """One green polygon on the map (see SqlSectorHistoryRepository.list_map_items)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    geom_geojson: dict[str, Any]
    year_a: int
    year_b: int
    status: str
    has_changes: Optional[bool] = None
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


class ReviewRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    comment: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: Optional[datetime] = None


class ParcelDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    change_type: str
    validation_status: str
    cadastral_code: Optional[str] = None
    probability: Optional[float] = None
    area_m2: Optional[float] = None
    construction_type: Optional[str] = None
    parcel_geom_geojson: Optional[dict[str, Any]] = None
    validated_by_username: Optional[str] = None
    validated_at: Optional[datetime] = None
    reviews: List[ReviewRecord] = []


class RunDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alignment_method: str
    created_at: Optional[datetime] = None
    alignment_quality_level: Optional[str] = None
    alignment_cc: Optional[float] = None
    alignment_residual_m: Optional[float] = None
    alignment_is_main: bool = False
    parcels: List[ParcelDetail] = []


class ProcessedSectorDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    runs: List[RunDetail] = []
