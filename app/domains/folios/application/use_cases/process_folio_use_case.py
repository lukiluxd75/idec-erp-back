"""
Background pipeline for one uploaded folio: reads its photos, hands them to
FolioExtractor (OCR + OpenCV + rules, no database) and stores the result.

Runs outside any request (BackgroundTasks), so every failure ends up stored on
the folio -- nothing here is allowed to escape.
"""
import logging
from typing import Optional

from app.core.errors.exceptions import DomainException
from app.domains.folios.application.folio_extractor import FolioExtractor
from app.domains.folios.domain.entities.folio import FolioStatus
from app.domains.folios.domain.ports.asiento_structurer_port import AsientoStructurerPort
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort
from app.domains.folios.domain.ports.ocr_port import OcrPort
from app.domains.folios.domain.ports.page_image_port import PageImagePort

logger = logging.getLogger("uvicorn.error")


class ProcessFolioUseCase:
    def __init__(
        self,
        repository: FolioRepositoryPort,
        ocr: OcrPort,
        images: PageImagePort,
        structurer: Optional[AsientoStructurerPort],
        confidence_threshold: float,
    ):
        self._repo = repository
        self._extractor = FolioExtractor(ocr, images, structurer, confidence_threshold)

    def execute(self, folio_id: str) -> None:
        folio = self._repo.get_for_processing(folio_id)
        if folio is None or folio.status == FolioStatus.CONFIRMED:
            return
        try:
            self._repo.mark_processing(folio_id)
            outcomes = []
            pages = self._repo.get_page_bytes_for_processing(folio_id)
            # The photos are in memory now; let go of the database before the OCR starts.
            self._repo.end_read()
            for page_index, content, _mime in pages:
                outcome = self._extractor.process_page(page_index, content)
                self._repo.save_page_result(
                    folio_id,
                    page_index,
                    upright_jpeg=outcome.upright,
                    rotation_deg=outcome.rotation_deg,
                    detected_page_number=outcome.layout.page_number if outcome.layout else None,
                    diagnostics=outcome.diagnostics,
                )
                outcomes.append(outcome)
            data, status, fill_log = self._extractor.assemble(outcomes)
            self._repo.save_extraction(folio_id, data, status, (data["matricula"] or {}).get("numero"), fill_log)
        except DomainException as exc:
            logger.warning("Folio %s: procesamiento fallido: %s", folio_id, exc.message)
            self._repo.mark_failed(folio_id, exc.message)
        except Exception:
            logger.exception("Folio %s: error inesperado al procesar", folio_id)
            self._repo.mark_failed(folio_id, "Error inesperado al procesar el folio. Intente reprocesarlo.")
