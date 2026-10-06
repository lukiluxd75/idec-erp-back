"""
The tax receipt lane's reading, end to end: the same PaddleOCR service the folio
lane uses (borrowed through the folios contract, CLAUDE.md §2), the FUR rules,
and only for what the rules could not fill, one call to qwen3-vl:4b on the
architects' PCs.

Why it is fast: no queue and no dispatcher poll -- the photo is OCR'd here and
the LLM sees text, not pixels. That is the whole difference with the digitization
lane this replaces, which had to wait for a worker to pick the job up and then
made the model read the image.
"""
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.core.config.settings import settings
from app.domains.folder_analysis.domain.exceptions import TaxStructurerUnavailableException
from app.domains.folder_analysis.domain.ports import TaxExtractionPort, TaxStructurerPort
from app.domains.folder_analysis.domain.services.fur_parser import FurReading, missing_fields, parse_fur
from app.domains.folder_analysis.domain.services.tax_result_mapper import to_tax_receipt_template
from app.domains.folder_analysis.domain.services.text import contains
from app.domains.folios.contracts import read_page_text

logger = logging.getLogger("uvicorn.error")

_TAXPAYER_KEYS = ("type", "id_number", "name")


class OcrTaxExtractor(TaxExtractionPort):
    """Stateless. `read_page` is the OCR step, injected so the rules can be
    tested without the service."""

    def __init__(
        self,
        structurer: Optional[TaxStructurerPort] = None,
        confidence_threshold: Optional[float] = None,
        read_page: Optional[Callable[[bytes, str], Any]] = None,
    ):
        self._structurer = structurer
        self._threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.TAX_RECEIPT_CONFIDENCE_THRESHOLD
        )
        self._read_page = read_page or read_page_text

    def extract(
        self,
        pages: Sequence[bytes],
        on_page: Optional[Callable[[int], None]] = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        blocks = []
        for index, content in enumerate(pages):
            blocks.append(self._read_page(content, f"impuesto_p{index + 1}.jpg").blocks)
            if on_page is not None:
                on_page(index)

        reading = parse_fur(blocks, self._threshold)
        filled = self._fill_gaps_with_llm(reading)
        return to_tax_receipt_template(reading, self._threshold, filled), reading.observations

    def _fill_gaps_with_llm(self, reading: FurReading) -> List[str]:
        """Asks for the fields the rules left empty, and keeps only the values
        that are literally in the OCR text -- the model may restructure what was
        read, never add to it. Returns the keys it actually filled."""
        missing = missing_fields(reading)
        if not missing or self._structurer is None or not self._structurer.is_configured():
            return []

        text = "\n".join(reading.lines)
        try:
            proposal = self._structurer.structure(text, missing)
        except TaxStructurerUnavailableException as exc:
            reading.observations.append(f"No se pudo usar IA para completar los datos: {exc.message}")
            return []

        filled: List[str] = []
        discarded: List[str] = []
        for key in missing:
            value = proposal.get(key)
            if key == "taxpayer":
                filled.extend(self._fill_taxpayer(reading, value, text, discarded))
                continue
            accepted = self._accept(value, text, discarded, key)
            if accepted is not None:
                reading.data[key] = accepted
                filled.append(key)

        if filled:
            reading.observations.append(
                f"La IA completó {len(filled)} campo(s) a partir del texto leído "
                f"({', '.join(filled)}): verifíquelos contra la foto."
            )
        if discarded:
            logger.info("Folder analysis: impuesto, valores descartados de la IA: %s", "; ".join(discarded))
        return filled

    def _fill_taxpayer(
        self, reading: FurReading, value: Any, text: str, discarded: List[str]
    ) -> List[str]:
        if not isinstance(value, dict):
            return []
        filled = []
        for key in _TAXPAYER_KEYS:
            if reading.data["taxpayer"].get(key) is not None:
                continue
            accepted = self._accept(value.get(key), text, discarded, f"taxpayer.{key}")
            if accepted is not None:
                reading.data["taxpayer"][key] = accepted
                filled.append(f"taxpayer.{key}")
        return filled

    @staticmethod
    def _accept(value: Any, text: str, discarded: List[str], key: str) -> Optional[str]:
        """The proposed value, or None when it is empty or not on the photo."""
        if value is None or isinstance(value, (dict, list)):
            return None
        candidate = str(value).strip()
        if not candidate:
            return None
        if not contains(candidate, text):
            discarded.append(f"{key}='{candidate}' (no está en el texto leído)")
            return None
        return candidate
