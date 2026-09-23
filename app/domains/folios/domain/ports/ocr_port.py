from abc import ABC, abstractmethod
from typing import List

from app.domains.folios.domain.entities.ocr_block import OcrBlock


class OcrPort(ABC):
    """Port over the text-recognition engine. Today the only adapter is the
    external GAMC OCR service (infrastructure/gamc_ocr_client.py) -- the same one
    resolutions/geoextraction call from the browser, here called server-side.
    Implementations raise OcrUnavailableException, never a raw network error."""

    @abstractmethod
    def read(self, image_bytes: bytes, filename: str = "pagina.jpg") -> List[OcrBlock]:
        """Text blocks (with axis-aligned boxes in the image's own pixel frame)."""
