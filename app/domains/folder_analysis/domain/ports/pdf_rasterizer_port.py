from abc import ABC, abstractmethod
from typing import List


class PdfRasterizerPort(ABC):
    """Turns a PDF into one photo per page.

    A folio scanned at a counter, a comprobante downloaded from the bank, a plano
    exported from CAD: they arrive as PDFs, and everything this module does --
    sorting into lanes, reading with OCR, the architects' PCs -- works on one
    image per page. So a PDF becomes exactly what a phone would have taken, and
    nothing downstream has to know it was ever a PDF."""

    @abstractmethod
    def pages(self, content: bytes, max_pages: int) -> List[bytes]:
        """The pages of `content` as JPEGs, in reading order.

        Raises InvalidCaptureException if the file is not a readable PDF, if it
        is protected by a password, or if it has more than `max_pages` pages."""
