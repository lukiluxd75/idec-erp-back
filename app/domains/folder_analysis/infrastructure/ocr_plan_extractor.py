"""
The plano lane, read here on the server with the GAMC PaddleOCR service and
OpenCV -- the same two tools the folio and the comprobante are read with, and
the same ones the Resoluciones P.H. screen already uses on a plano in the
browser.

It replaces the vision model on the architects' PCs. That path cost minutes per
sheet: the page was queued, waited for a free PC, and `qwen3-vl` then read the
whole drawing pixel by pixel to transcribe it. The OCR service reads the text of
a sheet in seconds, and the grid lines -- the part a text OCR cannot give -- come
from OpenCV, which is what they are for.

What it answers is deliberately unchanged: the text, the labelled values and the
tables, in the same shape the model used to return, so the review screen, the
stored documents and everything downstream keep working.
"""
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.domains.folder_analysis.domain.ports import ServerReadingPort
from app.domains.folder_analysis.domain.services import plan_survey
from app.domains.folder_analysis.domain.services.plan_layout import TableRegion, read_page, table_regions
from app.domains.folder_analysis.infrastructure import opencv_plan_reader
from app.domains.folder_analysis.infrastructure.drawing_reader import DrawingReader
from app.domains.folios.contracts import read_page_text

logger = logging.getLogger("uvicorn.error")

ENGINE = "paddleocr+opencv"

# Under this, the OCR is reading the drawing's strokes as if they were letters.
LOW_CONFIDENCE = 0.6


class OcrPlanExtractor(ServerReadingPort):
    """`read_page` is injected so the lane can be tested without the OCR service,
    the same way the comprobante's extractor does it."""

    def __init__(self, read_page: Optional[Callable[..., Any]] = None):
        self._read_page = read_page or read_page_text
        self._drawing = DrawingReader(self._read_page)

    def extract(
        self,
        pages: Sequence[bytes],
        on_page: Optional[Callable[[int], None]] = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        results: List[Dict[str, Any]] = []
        observations: List[str] = []

        for index, content in enumerate(pages):
            number = index + 1
            results.append(self._read_sheet(content, number, observations))
            if on_page is not None:
                on_page(index)

        return self._document(results, observations), observations

    def _read_sheet(self, content: bytes, number: int, observations: List[str]) -> Dict[str, Any]:
        # Straighten first: the OCR is given the same page the lines are measured
        # on, or the blocks and the grid would not line up.
        straightened = opencv_plan_reader.safe_deskew(content, number)
        image = straightened.image if straightened else content

        page = self._read_page(image, f"plano_p{number}.jpg")
        if not page.blocks:
            observations.append(f"La página {number} no tiene texto que el OCR pueda leer.")
            return {"page": number, "document_type": "", "full_text": "", "fields": [], "tables": []}

        confidences = [b.confidence for b in page.blocks]
        if sum(confidences) / len(confidences) < LOW_CONFIDENCE:
            observations.append(
                f"La página {number} se leyó con poca claridad: compare el texto con la foto."
            )

        sheet = read_page(page.blocks, self._grids(straightened, page))
        sheet["page"] = number
        self._read_drawing(sheet, straightened, page)
        return sheet

    def _read_drawing(self, sheet: Dict[str, Any], straightened, page) -> None:
        """The measures written on the drawing, for a sheet whose lot is not given by
        a table of UTM coordinates. They travel with the page (`dimensions`, `street`)
        so the sides can be worked out after the reading, once the surface the plano
        declares is known."""
        if straightened is None or len(plan_survey.parse_vertices(sheet["full_text"])) >= 3:
            return
        try:
            frame = opencv_plan_reader.fit_to(straightened.frame, page.width, page.height)
            drawing = self._drawing.read(frame, page.blocks)
        except Exception:
            logger.exception("Folder analysis: no se pudo leer el dibujo del plano")
            return
        if drawing["dimensions"]:
            sheet["dimensions"] = drawing["dimensions"]
        if drawing["street"]:
            sheet["street"] = drawing["street"]

    def _grids(self, straightened, page) -> List[Tuple[TableRegion, List[float]]]:
        """Every cuadro of the sheet with its column lines, in the frame the OCR
        answered in. No OpenCV, no cuadros -- the text still reads fine."""
        if straightened is None:
            return []
        try:
            frame = opencv_plan_reader.fit_to(straightened.frame, page.width, page.height)
            regions = table_regions(opencv_plan_reader.row_rules(frame), page.height)
            return [(region, opencv_plan_reader.column_lines(frame, region)) for region in regions]
        except Exception:
            logger.exception("Folder analysis: no se pudieron detectar los cuadros del plano")
            return []

    def _document(self, pages: List[Dict[str, Any]], observations: List[str]) -> Dict[str, Any]:
        tables = sum(len(page["tables"]) for page in pages)
        return {
            "document_type": next((p["document_type"] for p in pages if p["document_type"]), "Plano"),
            "full_text": "\n\n".join(p["full_text"] for p in pages if p["full_text"]).strip(),
            "pages": pages,
            "reading": {
                "engine": ENGINE,
                "pages_read": len(pages),
                "tables_found": tables,
                "observations": observations,
            },
        }
