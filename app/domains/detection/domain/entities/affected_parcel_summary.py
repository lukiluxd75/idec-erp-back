"""Read projection of `detection_results.affected_parcel`, ordered the same
way `detection_results.detection` was created (i.e. the same order as the
engine's `cambios[]`/`reporte_arquitecto[]` for that job) — lets the frontend
attach `affected_parcel_id` to the raw engine row it already renders, so the
architect's review/feedback actions have something to call. No SQLAlchemy, no
FastAPI."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class AffectedParcelSummary:
    id: int
    detection_id: Optional[int]
    cadastral_code: Optional[str]
    change_type: str
    validation_status: str
