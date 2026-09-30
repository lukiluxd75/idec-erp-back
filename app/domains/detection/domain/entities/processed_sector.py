"""Entity for a row of `detection_results.processed_sector` — one GPU detection
job persisted in the ERP. No SQLAlchemy, no FastAPI (see CLAUDE.md §3)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ProcessedSector:
    id: int
    year_a: int
    year_b: int
    status: str
    progress_pct: int
    campaign_id: Optional[int] = None
    name: Optional[str] = None
    has_changes: Optional[bool] = None
    n_affected_parcels: int = 0
    n_new_parcels: int = 0
    n_removed_parcels: int = 0
    n_changed_parcels: int = 0
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


@dataclass
class SectorResumeContext:
    """What ResumeSectorValidationUseCase needs to re-fetch a sector's most
    recent run's persisted `reporte.json` artifact -- see
    ProcessedSectorRepositoryPort.get_resume_context."""

    job_id: Optional[str]
    status: str
