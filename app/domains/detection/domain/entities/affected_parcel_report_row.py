"""One row of the campaign parcels report export (see
ExportCampaignReportUseCase) -- confirmed/rejected affected_parcel only,
never pending: an unverified finding doesn't belong in a fiscal report. No
SQLAlchemy, no FastAPI (see CLAUDE.md §3)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class AffectedParcelReportRow:
    sector_id: int
    sector_name: Optional[str]
    year_a: int
    year_b: int
    campaign_code: Optional[str]
    cadastral_code: Optional[str]
    change_type: str
    construction_type: Optional[str]
    validation_status: str
    rejection_comment: Optional[str]
    probability_pct: Optional[int]
    validated_by_username: Optional[str]
    validated_at: Optional[datetime]
    lon: Optional[float]
    lat: Optional[float]
