import logging
from typing import Any, Optional

from app.domains.detection.domain.ports.detection_engine_port import DetectionEnginePort
from app.domains.detection.domain.ports.processed_sector_repository_port import (
    ProcessedSectorRepositoryPort,
)

logger = logging.getLogger("uvicorn.error")


class StartDetectionJobUseCase:
    """Queues a WMS change-detection job on the GPU engine and immediately
    persists its `processed_sector` (see ProcessedSectorRepositoryPort.start) so
    the run is trackable in `detection_results` before any progress/result poll
    happens."""

    def __init__(self, engine: DetectionEnginePort, repository: ProcessedSectorRepositoryPort):
        self._engine = engine
        self._repository = repository

    def execute(self, payload: dict[str, Any], created_by_sub: Optional[str] = None) -> dict[str, Any]:
        # ERP-only bookkeeping, unknown to the GPU engine -- see DetectChangesRequest.
        campaign_id = payload.pop("campaign_id", None)

        engine_response = self._engine.start_detect_wms_async(payload)
        job_id = engine_response.get("job_id")

        try:
            sector = self._repository.start(
                year_a=payload["year_ref"],
                year_b=payload["year_mov"],
                job_id=job_id,
                request_params=payload,
                bbox=payload.get("bbox"),
                polygon=payload.get("polygon"),
                campaign_id=campaign_id,
                created_by_sub=created_by_sub,
            )
        except Exception:
            # The GPU job is already running at this point; failing to persist
            # its processed_sector must not fail the request the frontend is
            # waiting on for job_id. IngestDetectionResultUseCase simply becomes
            # a no-op later for a job_id it can't find (see find_by_job_id) --
            # the GPU run itself is not lost, only its ERP-side bookkeeping.
            logger.exception("Failed to persist processed_sector for job %s", job_id)
            return engine_response

        return {**engine_response, "processed_sector_id": sector.id}
