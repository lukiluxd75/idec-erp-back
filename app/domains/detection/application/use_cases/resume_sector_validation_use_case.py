import logging
from typing import Any, Optional

from app.domains.detection.domain.ports.detection_engine_port import DetectionEnginePort
from app.domains.detection.domain.ports.processed_sector_repository_port import (
    ProcessedSectorRepositoryPort,
)

logger = logging.getLogger("uvicorn.error")


class ResumeSectorValidationUseCase:
    """Backs "Continuar validación": re-fetches a sector's persisted
    `reporte.json` artifact (the GPU engine's own full result file, saved
    once per run) and enriches it exactly like `job_result` does for a live
    job -- so the frontend can load it into the very same Hallazgos table it
    already renders right after a fresh detection finishes, instead of
    needing a second, separate read-only view. Works for any past run: the
    file lives on the engine's filesystem, not in its transient job-queue
    state, so this does not require the engine to still be "tracking" the job."""

    def __init__(self, engine: DetectionEnginePort, repository: ProcessedSectorRepositoryPort):
        self._engine = engine
        self._repository = repository

    def execute(self, processed_sector_id: int) -> Optional[dict[str, Any]]:
        context = self._repository.get_resume_context(processed_sector_id)
        if context is None or not context.job_id:
            return None

        result = self._engine.fetch_json(f"/outputs/{context.job_id}/result/reporte.json")

        result["processed_sector_id"] = processed_sector_id
        result["processed_sector_status"] = context.status
        # reporte.json has no `urls` field (that only exists on the engine's
        # live job-result response) -- without this the frontend's asset
        # gallery has nothing to hydrate and the before/after images are
        # simply blank on a resumed sector.
        if context.urls:
            result["urls"] = context.urls

        # Same positional enrichment as job_result's own response (see
        # endpoints/detection.py) -- list_affected_parcels() returns rows in
        # the same order/length as this run's cambios[]/reporte_arquitecto[].
        try:
            parcels = self._repository.list_affected_parcels(processed_sector_id)
            for array_key in ("cambios", "reporte_arquitecto"):
                rows = result.get(array_key) or []
                for row, parcel in zip(rows, parcels):
                    row["affected_parcel_id"] = parcel.id
                    row["validation_status"] = parcel.validation_status
        except Exception:
            logger.exception(
                "Failed to attach affected_parcel_id while resuming validation for sector %s",
                processed_sector_id,
            )

        return result
