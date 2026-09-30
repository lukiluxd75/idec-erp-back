"""Entities for `alignment_results.alignment_block`/`alignment_control_point`
-- manual, block-by-block georeferencing of a year's imagery against the
fixed 2015 reference layer (see doc/alignment_schema.sql). No SQLAlchemy, no
FastAPI. Independent of the `detection` domain -- not imported by it, does
not import it."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ControlPointRecord:
    order_index: int
    lon_ref: float
    lat_ref: float
    lon_mov: float
    lat_mov: float


@dataclass
class AlignmentBlock:
    """One row of `alignment_block`, without its control points -- what the
    map needs to render every block for a given year (see
    AlignmentBlockRepositoryPort.list_by_year)."""

    id: int
    year: int
    geom_geojson: Dict[str, Any]
    status: str
    transform_method: str
    rmse_m: Optional[float] = None
    cropped_image_path: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: Optional[datetime] = None
    confirmed_by_username: Optional[str] = None
    confirmed_at: Optional[datetime] = None


@dataclass
class AlignmentBlockDetail(AlignmentBlock):
    """AlignmentBlock plus its control points and the fitted transform
    parameters -- the single-block detail view."""

    transform_params: Optional[Dict[str, Any]] = None
    control_points: List[ControlPointRecord] = field(default_factory=list)


@dataclass
class AlignmentCoverage:
    """How much of Cercado is already aligned for a given year (see
    AlignmentBlockRepositoryPort.coverage) -- confirmed blocks only."""

    year: int
    n_blocks: int
    covered_area_m2: float
