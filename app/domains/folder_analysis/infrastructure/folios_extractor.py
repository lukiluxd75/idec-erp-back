from typing import Any, Dict, List, Sequence, Tuple

from app.domains.folder_analysis.domain.ports import FolioExtractionPort
from app.domains.folder_analysis.domain.services.folio_result_mapper import to_folio_template
from app.domains.folios.contracts import extract_folio


class FoliosExtractor(FolioExtractionPort):
    """Adapter over the folios domain's public contract (CLAUDE.md §2): the folio
    lane reads its pages with that pipeline (GAMC OCR + OpenCV + rule parsers)
    and stores the result in its own shape."""

    def extract(self, pages: Sequence[bytes]) -> Tuple[Dict[str, Any], List[str]]:
        extraction = extract_folio(pages)
        return to_folio_template(extraction.data, extraction.fill_log), extraction.observations
