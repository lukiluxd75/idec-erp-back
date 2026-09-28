from abc import ABC, abstractmethod
from typing import Any, Dict, Sequence


class TaxStructurerPort(ABC):
    """The optional LLM step of the tax receipt lane: it is handed the OCR text
    of the receipt and the keys the rules could not fill, and answers with those
    keys. It only restructures text that is already on the photo -- the caller
    discards anything that is not literally in the OCR text.

    Optional on purpose: with no PC available the lane still stores what the
    rules read and says so in the observations."""

    @abstractmethod
    def is_configured(self) -> bool:
        """False when there is nowhere to ask, so the caller skips the step."""

    @abstractmethod
    def structure(self, ocr_text: str, missing: Sequence[str]) -> Dict[str, Any]:
        """{key: value} for the keys in `missing` that it could find in
        `ocr_text`. Raises TaxStructurerUnavailableException when no PC answered."""
