"""Entity for a row of `detection_results.processed_sector` — one GPU detection
job persisted in the ERP. No SQLAlchemy, no FastAPI (see CLAUDE.md §3)."""
from dataclasses import dataclass, field
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
    ProcessedSectorRepositoryPort.get_resume_context.

    `urls` is the run's own sector_artifact rows (kind -> proxy-ready path,
    already keyed like the frontend expects -- aligned_a/aligned_b/
    panel_resultado/align_check). reporte.json itself has no `urls` field
    (that only exists on the engine's live job-result response, which is
    long gone by the time an architect resumes a pending sector), so this is
    the only way to recover the before/after images for that run."""

    job_id: Optional[str]
    status: str
    urls: dict = field(default_factory=dict)
