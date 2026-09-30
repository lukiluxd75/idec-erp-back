from abc import ABC, abstractmethod
from typing import Any, List, Optional

from app.domains.detection.domain.entities.affected_parcel_summary import AffectedParcelSummary
from app.domains.detection.domain.entities.processed_sector import ProcessedSector, SectorResumeContext


class ProcessedSectorRepositoryPort(ABC):
    """
    Port the `detection` infrastructure must implement (see CLAUDE.md §3) to
    persist a GPU detection pipeline run into `detection_results`. application/
    only knows this interface, never the schema's tables or GeoAlchemy2 (today:
    Postgres/PostGIS — see SqlProcessedSectorRepository).

    Covers the write path exercised when the ERP starts a job and later reads
    its result, plus the `affected_parcel` read projection the result screen
    needs to attach ids to. `campaign` has its own CampaignRepositoryPort;
    `architect_review` has its own AffectedParcelReviewPort.
    """

    @abstractmethod
    def start(
        self,
        year_a: int,
        year_b: int,
        job_id: str,
        request_params: dict[str, Any],
        bbox: Optional[list[float]] = None,
        polygon: Optional[list[list[float]]] = None,
        campaign_id: Optional[int] = None,
        name: Optional[str] = None,
        created_by_sub: Optional[str] = None,
    ) -> ProcessedSector:
        """Create the `processed_sector` row for a job the engine just accepted
        (`geom` from `bbox` or `polygon`, exactly one of which the request always
        carries — see DetectChangesRequest), plus its first `processing_run`
        (params carries the request body + job_id, the only place that
        correlates a run with the engine's job — see infrastructure/models.py).
        `created_by_sub` is the authenticated user's Keycloak `sub`; the
        implementation resolves it to `public.users.id` for `created_by`."""

    @abstractmethod
    def find_by_job_id(self, job_id: str) -> Optional[ProcessedSector]:
        """Look up the processed_sector started for a given engine job_id."""

    @abstractmethod
    def is_ingested(self, processed_sector_id: int) -> bool:
        """True once a result has already been written for this sector (the
        job/result endpoints are polled repeatedly by the frontend; ingestion
        must be idempotent)."""

    @abstractmethod
    def ingest_result(
        self, processed_sector_id: int, engine_result: dict[str, Any], engine_steps: list[dict[str, Any]]
    ) -> ProcessedSector:
        """Write alignment, detections, affected parcels, artifacts and
        processing history from a completed `GET .../result` (+ its `progress`
        steps for processing_history), and update the sector's own status/counts.
        If a manual alignment is pending (see record_manual_alignment), this
        creates a NEW processing_run + detection/affected_parcel batch on top
        of it instead of creating a fresh auto_ecc alignment -- the engine
        re-ran detection on the newly-aligned images, so this is a second run,
        kept alongside the first as history, not a replacement of it."""

    @abstractmethod
    def list_affected_parcels(self, processed_sector_id: int) -> List[AffectedParcelSummary]:
        """affected_parcel rows for the sector's MOST RECENT processing_run
        only (not older, superseded runs), in creation order -- matching the
        order/length of whatever `cambios[]`/`reporte_arquitecto[]` the latest
        `GET .../result` call returned, so index i here is index i there (see
        job_result's response enrichment)."""

    @abstractmethod
    def get_resume_context(self, processed_sector_id: int) -> Optional[SectorResumeContext]:
        """The engine job_id behind the sector's most recent processing_run
        (None if that run predates job_id being recorded) plus the sector's
        current status -- see ResumeSectorValidationUseCase, which uses the
        job_id to re-fetch that run's persisted `reporte.json` artifact
        instead of needing the engine's job to still be tracked as "active".
        None if the sector itself doesn't exist."""

    @abstractmethod
    def record_manual_alignment(
        self,
        processed_sector_id: int,
        points: List[dict],
        gcp_method: str,
        warp_matrix: Optional[dict] = None,
    ) -> None:
        """Called right after the GPU engine confirms an align-manual/apply
        (see the `/jobs/{job_id}/manual-align/apply` endpoint): records the
        architect's control points as a new `alignment` (method='manual_gcp')
        + `control_point` rows, and resets the sector back to 'detecting' so
        the next ingested result (the engine re-runs detection on apply) is
        treated as a fresh run instead of being skipped by is_ingested().
        cc/residual_m are deliberately not parameters here -- apply's own
        response does not carry them (verified against a real one), only the
        later re-run's result does, so ingest_result() fills them in and only
        then decides which of the sector's alignments is now the "best" one
        (lower residual_m wins -- both auto_ecc and manual_gcp report it in
        the same units, verified against real engine responses for each;
        purely bookkeeping on `alignment.is_accepted`, does not affect which
        run's detections the sector counts or review screen use)."""
