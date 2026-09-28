"""Entity for a row of `detection_results.architect_review` — an architect's
decision on an `affected_parcel`. No SQLAlchemy, no FastAPI."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ArchitectReview:
    id: int
    affected_parcel_id: int
    action: str
    comment: Optional[str] = None
    created_at: Optional[datetime] = None
