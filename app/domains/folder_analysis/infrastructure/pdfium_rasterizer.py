import logging

from typing import List, Optional

import cv2
import numpy as np
import pypdfium2 as pdfium

from app.domains.folder_analysis.domain.exceptions import InvalidCaptureException
from app.domains.folder_analysis.domain.ports import PdfRasterizerPort

logger = logging.getLogger("uvicorn.error")

TARGET_LONG_SIDE = 2000
MIN_DPI = 150
MAX_LONG_SIDE = 4500
MAX_SCALE = 4.0  # a small page (a receipt) is not worth more than 288 dpi


class PdfiumRasterizer(PdfRasterizerPort):
    """PDF pages as JPEGs, rendered with PDFium (the engine Chrome shows PDFs
    with). It is a self-contained wheel: no Ghostscript, no poppler, nothing to
    install on the server next to Python."""

    def __init__(self, jpeg_quality: int = 88):
        self._jpeg_quality = jpeg_quality

    def pages(self, content: bytes, max_pages: Optional[int] = None) -> List[bytes]:
        try:
            document = pdfium.PdfDocument(content)
            total = len(document)
        except pdfium.PdfiumError as exc:
            # Password, broken xref, not a PDF at all: all the same to the architect, who only needs to know this file cannot be used.
            logger.info("Folder analysis: PDF ilegible (%s)", exc)
            raise InvalidCaptureException(
                "El PDF no se pudo abrir. Si tiene contraseña, quítesela y vuelva a subirlo."
            ) from None

        if total == 0:
            raise InvalidCaptureException("El PDF no tiene páginas.")
        if max_pages is not None and total > max_pages:
            raise InvalidCaptureException(
                f"El PDF tiene {total} páginas y se admiten como máximo {max_pages}. "
                "Separe el documento y suba las páginas que necesita."
            )

        try:
            document.init_forms()
        except Exception:
            logger.debug("Folder analysis: el PDF no trae formularios que dibujar")

        images = []
        for index in range(total):
            page = document[index]
            width, height = page.get_size()
            scale = self._scale_for(max(width, height, 1))
            try:
                image = page.render(scale=scale).to_numpy()
            except pdfium.PdfiumError as exc:
                logger.info("Folder analysis: página %d del PDF ilegible (%s)", index + 1, exc)
                raise InvalidCaptureException(
                    f"No se pudo leer la página {index + 1} del PDF."
                ) from None
            images.append(self._encode(image, index))
        return images

    @staticmethod
    def _scale_for(long_side_pt: float) -> float:
        """How much to blow up one page, from its size in points (1/72 inch)."""
        scale = max(TARGET_LONG_SIDE / long_side_pt, MIN_DPI / 72.0)
        return min(scale, MAX_LONG_SIDE / long_side_pt, MAX_SCALE)

    def _encode(self, image: np.ndarray, index: int) -> bytes:
        # PDFium hands back BGR, which is the order OpenCV writes.
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
        if not ok:
            raise InvalidCaptureException(f"No se pudo convertir la página {index + 1} del PDF.")
        return encoded.tobytes()
