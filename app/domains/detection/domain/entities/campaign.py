"""Entity for a row of `detection_results.campaign` — a period (e.g. a
quarter) that groups processed sectors. No SQLAlchemy, no FastAPI."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class Campaign:
    id: int
    code: str
    name: str
    status: str
    n_sectors: int
    n_affected_parcels: int
    description: Optional[str] = None
    # Fixed for the campaign's whole life (see doc/bdd.sql's 2026-09-29 patch)
    # -- the frontend locks its year selectors to these once a campaign is
    # picked. Optional only for campaigns created before that patch.
    year_a: Optional[int] = None
    year_b: Optional[int] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
