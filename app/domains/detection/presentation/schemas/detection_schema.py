from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class DetectChangesRequest(BaseModel):
    """Payload forwarded to the GPU detect-changes-wms-async endpoint."""

    year_ref: int = Field(..., examples=[2018])
    year_mov: int = Field(..., examples=[2024])
    bbox: Optional[list[float]] = Field(None, description="CRS84 [minLon,minLat,maxLon,maxLat]")
    polygon: Optional[list[list[float]]] = Field(None, description="Ring [[lon,lat],...]")
    auto_resolution: bool = True
    target_gsd_m: float = 0.3
    max_px: int = 4096
    min_area_m2: float = 15.0
    min_diff: float = 0.25
    gpu: int = 0
    min_prob_pct: float = 40.0
    predios_buffer_m: float = 2.0
    points_per_side: int = 8
    campaign_id: Optional[int] = Field(None, description="detection_results.campaign id, if any")


class CampaignCreateRequest(BaseModel):
    """Backs the "+ Nueva campaña" quick-create on the detection start screen.
    `year_a`/`year_b` are fixed for the campaign's whole life (see
    doc/bdd.sql's 2026-09-29 patch) -- the frontend locks its year selectors
    to them once this campaign is picked."""

    code: str = Field(..., max_length=30, examples=["2026-Q4"])
    name: str = Field(..., max_length=150, examples=["Cuarto trimestre 2026"])
    year_a: int = Field(..., examples=[2018])
    year_b: int = Field(..., examples=[2024])
    description: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class CampaignSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    status: str
    n_sectors: int
    n_affected_parcels: int
    description: Optional[str] = None
    year_a: Optional[int] = None
    year_b: Optional[int] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class ReviewAffectedParcelRequest(BaseModel):
    """Confirm (with construction_type) or reject (with an optional audit
    comment) an affected_parcel. construction_type is a short title -- either
    one of ReviewAffectedParcelUseCase's ALLOWED_CONSTRUCTION_TYPES, or a
    custom one the architect typed after picking "Otro" in the frontend's
    dropdown (see CONSTRUCTION_TYPE_MAX_LENGTH there); not a fixed enum here
    since that custom text is a real, valid value."""

    action: str = Field(..., pattern="^(confirm|reject)$")
    comment: Optional[str] = None
    construction_type: Optional[str] = Field(None, max_length=30)


class ArchitectReviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    affected_parcel_id: int
    action: str
    comment: Optional[str] = None
    created_at: Optional[datetime] = None


class AlignManualRequest(BaseModel):
    points: list[dict[str, float]] = Field(..., min_length=3)
    method: str = Field("affine", pattern="^(affine|homography)$")


class EngineProxyInfo(BaseModel):
    engine_url: str
    reachable: bool
    detail: Any = None
