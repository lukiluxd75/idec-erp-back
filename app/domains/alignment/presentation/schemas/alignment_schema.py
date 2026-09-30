from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ControlPointInput(BaseModel):
    lon_ref: float
    lat_ref: float
    lon_mov: float
    lat_mov: float


class CreateAlignmentBlockRequest(BaseModel):
    year: int = Field(..., examples=[2018])
    ring: List[List[float]] = Field(..., description="Polygon ring [[lon,lat], ...], min 3 points")
    control_points: List[ControlPointInput] = Field(..., min_length=3)


class UpdateAlignmentBlockRequest(BaseModel):
    ring: List[List[float]] = Field(..., description="Polygon ring [[lon,lat], ...], min 3 points")
    control_points: List[ControlPointInput] = Field(..., min_length=3)


class ControlPointSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_index: int
    lon_ref: float
    lat_ref: float
    lon_mov: float
    lat_mov: float


class AlignmentBlockSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    geom_geojson: dict[str, Any]
    status: str
    transform_method: str
    rmse_m: Optional[float] = None
    cropped_image_path: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: Optional[datetime] = None
    confirmed_by_username: Optional[str] = None
    confirmed_at: Optional[datetime] = None


class AlignmentBlockDetailSchema(AlignmentBlockSummary):
    transform_params: Optional[dict[str, Any]] = None
    control_points: List[ControlPointSummary] = []


class AlignmentCoverageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    n_blocks: int
    covered_area_m2: float
