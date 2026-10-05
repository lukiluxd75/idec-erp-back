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

It also lends the bare OCR step to lanes that read a different form with their
own rules (the tax receipt lane does), so they get the same PaddleOCR service
without a second client of their own:

    from app.domains.folios.contracts import read_page_text

    page = read_page_text(jpeg)   # page.blocks, page.width, page.height

Several OCR calls per photo: seconds, not milliseconds. Call it off the request
thread (BackgroundTasks), never inside a handler.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.core.config.settings import settings
from app.domains.folios.application.folio_extractor import FolioExtractor
from app.domains.folios.domain.entities.folio import FolioStatus
from app.domains.folios.presentation.deps import get_asiento_structurer, get_ocr, get_page_images

__all__ = ["FolioExtraction", "PageText", "TextBlock", "extract_folio", "read_page_text"]


@dataclass(frozen=True)
class FolioExtraction:
    data: Dict[str, Any]
    needs_review: bool
    fill_log: Dict[str, Any]

    @property
    def observations(self) -> List[str]:
        return list(self.data.get("observaciones") or [])


def extract_folio(
    pages: Sequence[bytes],
    on_page: Optional[Callable[[int], None]] = None,
) -> FolioExtraction:
    """Read one folio real from its photos, in scan order (page order is taken
    from the printed 'Pag X de N' when it can be read). Never raises for a
    photo it cannot read: that comes back as an observation.

    `on_page(index)` is called as each photo is finished, for a caller that
    wants to show progress while the rest are still running."""
    data, status, fill_log = FolioExtractor(
        ocr=get_ocr(),
        images=get_page_images(),
        structurer=get_asiento_structurer(),
        confidence_threshold=settings.FOLIOS_CONFIDENCE_THRESHOLD,
    ).extract(pages, on_page=on_page)
    return FolioExtraction(data=data, needs_review=status == FolioStatus.NEEDS_REVIEW, fill_log=fill_log)


@dataclass(frozen=True)
class TextBlock:
    """One text block of the OCR answer, as an axis-aligned box. The same value
    the folio parsers work with, published here so another domain can reason
    about position (labels and their values) without importing folios' insides."""

    text: str
    confidence: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class PageText:
    blocks: List[TextBlock]
    width: int
    height: int


def read_page_text(image: bytes, filename: str = "pagina.jpg") -> PageText:
    """OCR of one photo with the GAMC PaddleOCR service, normalized first (EXIF
    orientation and size cap) so the boxes are in the frame the caller would get
    from the same photo. Raises OcrUnavailableException (a DomainException) when
    the service cannot be reached; it never falls back to anything else.

    One OCR call: seconds. Off the request thread, like extract_folio."""
    jpeg, width, height = get_page_images().normalize(image)
    blocks = [
        TextBlock(b.text, b.confidence, b.x0, b.y0, b.x1, b.y1)
        for b in get_ocr().read(jpeg, filename)
    ]
    return PageText(blocks=blocks, width=width, height=height)
