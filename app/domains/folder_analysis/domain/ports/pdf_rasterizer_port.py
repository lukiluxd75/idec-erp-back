from abc import ABC, abstractmethod
from typing import List, Optional


class PdfRasterizerPort(ABC):
    """Turns a PDF into one photo per page.

    A folio scanned at a counter, a comprobante downloaded from the bank, a plano
    exported from CAD: they arrive as PDFs, and everything this module does --
    sorting into lanes, reading with OCR, the architects' PCs -- works on one
    image per page. So a PDF becomes exactly what a phone would have taken, and
    nothing downstream has to know it was ever a PDF."""

    @abstractmethod
    def pages(self, content: bytes, max_pages: Optional[int] = None) -> List[bytes]:
        """The pages of `content` as JPEGs, in reading order.

        `max_pages` en None es sin tope, que es como lo pide la bandeja: una
        carpeta entera escaneada de una sola vez es un caso normal, no un abuso.

        Raises InvalidCaptureException if the file is not a readable PDF, if it
        is protected by a password, or if it has more pages than `max_pages`."""
