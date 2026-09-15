from typing import Any, Optional

from pydantic import BaseModel, Field


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


class AlignManualRequest(BaseModel):
    points: list[dict[str, float]] = Field(..., min_length=3)
    method: str = Field("affine", pattern="^(affine|homography)$")


class EngineProxyInfo(BaseModel):
    engine_url: str
    reachable: bool
    detail: Any = None
