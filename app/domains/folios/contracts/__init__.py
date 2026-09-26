"""
Public entry point of the folios domain for other domains (CLAUDE.md §2).
It lends the folio reading pipeline -- OCR of the GAMC service + OpenCV column
detection + the rule parsers -- without touching the folios tables: the caller
keeps its own records and only gets the data back.

    from app.domains.folios.contracts import extract_folio

    extraction = extract_folio([page1_jpeg, page2_jpeg])
    extraction.data           # matricula, linderos, titularidad_dominio, ...
    extraction.needs_review   # some field was read with low confidence
    extraction.observations   # what to tell the architect

Several OCR calls per photo: seconds, not milliseconds. Call it off the request
thread (BackgroundTasks), never inside a handler.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from app.core.config.settings import settings
from app.domains.folios.application.folio_extractor import FolioExtractor
from app.domains.folios.domain.entities.folio import FolioStatus
from app.domains.folios.presentation.deps import get_asiento_structurer, get_ocr, get_page_images

__all__ = ["FolioExtraction", "extract_folio"]


@dataclass(frozen=True)
class FolioExtraction:
    data: Dict[str, Any]
    needs_review: bool
    # How every value was reached (OCR text per field, LLM proposals): for the
    # caller to store next to the data when it wants a fill log of its own.
    fill_log: Dict[str, Any]

    @property
    def observations(self) -> List[str]:
        return list(self.data.get("observaciones") or [])


def extract_folio(pages: Sequence[bytes]) -> FolioExtraction:
    """Read one folio real from its photos, in scan order (page order is taken
    from the printed 'Pag X de N' when it can be read). Never raises for a
    photo it cannot read: that comes back as an observation."""
    data, status, fill_log = FolioExtractor(
        ocr=get_ocr(),
        images=get_page_images(),
        structurer=get_asiento_structurer(),
        confidence_threshold=settings.FOLIOS_CONFIDENCE_THRESHOLD,
    ).extract(pages)
    return FolioExtraction(data=data, needs_review=status == FolioStatus.NEEDS_REVIEW, fill_log=fill_log)
