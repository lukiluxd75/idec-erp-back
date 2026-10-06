"""
The tax receipt lane reads its photo with PaddleOCR + the FUR rules instead of
the vision model on the architects' PCs. This turns that reading into the
TAX_RECEIPT_TEMPLATE the lane stores and the review screen renders, so nothing
downstream had to change -- the same thing folio_result_mapper does for folios.

What the rules give that the model never did -- per-field confidence, the
observations and the OCR text every value came from -- is kept under `reading`
for the review screen and the JSON tab.
"""
from typing import Any, Dict, Optional, Sequence

from app.domains.folder_analysis.domain.extraction_profiles import TAX_RECEIPT_TEMPLATE
from app.domains.folder_analysis.domain.services.fur_parser import (
    PARSER_VERSION,
    FurReading,
    low_confidence_fields,
)
from app.domains.folder_analysis.domain.services.result_merger import conform

# The parser lists the low-confidence fields in an observation, by key.
_LOW_CONFIDENCE_NOTE = "Campos con baja confianza de lectura:"


def to_tax_receipt_template(
    reading: FurReading,
    confidence_threshold: float,
    filled_by_ai: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """`reading` as parse_fur returns it -> the lane's stored shape."""
    result = conform(TAX_RECEIPT_TEMPLATE, reading.data)
    result["reading"] = {
        "source": "ocr_rules",
        "parser_version": PARSER_VERSION,
        # In the review form's own keys, so it can mark them without translating.
        "low_confidence_fields": low_confidence_fields(reading, confidence_threshold),
        "fields_filled_by_ai": list(filled_by_ai or []),
        "labels_not_found": sorted(
            {entry["campo"] for entry in reading.trace if entry.get("label") is None}
        ),
        "observations": [
            note for note in reading.observations if not note.startswith(_LOW_CONFIDENCE_NOTE)
        ],
        # Every line the OCR read, so nothing read from the photo is silently dropped: the JSON tab shows it next to the fields.
        "ocr_lines": list(reading.lines),
    }
    return result
