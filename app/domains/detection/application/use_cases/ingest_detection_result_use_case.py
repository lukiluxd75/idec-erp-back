from typing import Any, Optional

from app.domains.detection.domain.entities.processed_sector import ProcessedSector
from app.domains.detection.domain.ports.detection_engine_port import DetectionEnginePort
from app.domains.detection.domain.ports.processed_sector_repository_port import (
    ProcessedSectorRepositoryPort,
)


class IngestDetectionResultUseCase:
    """Persists a completed job's result into `detection_results`, the first
    time it is observed. Called from the `job_result` endpoint right after it
    fetches the result for the frontend — idempotent, since the frontend polls
    that same endpoint repeatedly (see ProcessedSectorRepositoryPort.is_ingested).

    Returns the sector whenever one exists for this job_id (freshly ingested or
    already ingested by a previous poll), so the endpoint can always attach
    `affected_parcel_id`/`validation_status` onto the response it returns to
    the frontend (see ProcessedSectorRepositoryPort.list_affected_parcels) --
    None only when the job was never started through this ERP."""

    def __init__(self, engine: DetectionEnginePort, repository: ProcessedSectorRepositoryPort):
        self._engine = engine
        self._repository = repository

    def execute(self, job_id: str, engine_result: dict[str, Any]) -> Optional[ProcessedSector]:
        sector = self._repository.find_by_job_id(job_id)
        if sector is None:
            # Job not started through this ERP's start_detect_wms endpoint (e.g.
            # a manual/lab call straight to the engine) -- nothing to attach it to.
            return None
        if self._repository.is_ingested(sector.id):
            return sector

        progress = self._engine.get_progress(job_id)
        steps = progress.get("steps") or []
        return self._repository.ingest_result(sector.id, engine_result, steps)
