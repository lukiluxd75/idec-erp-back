import cv2
import numpy as np

from app.domains.folder_analysis.domain.exceptions import InvalidCaptureException
from app.domains.folder_analysis.domain.ports import ThumbnailPort


class OpenCvThumbnail(ThumbnailPort):
    """Both sizes come out of the same decode: the thumbnail stored with the
    photo, and the web-sized copy the viewer reads from."""

    def __init__(self, max_side: int = 320, preview_max_side: int = 1600, jpeg_quality: int = 80):
        self._max_side = max_side
        self._preview_max_side = preview_max_side
        self._jpeg_quality = jpeg_quality

    def make(self, content: bytes) -> bytes:
        return self._resize(content, self._max_side, self._jpeg_quality)

    def preview(self, content: bytes) -> bytes:
        # A little more quality than the thumbnail: this is the copy the
        # architect reads the folio from.
        return self._resize(content, self._preview_max_side, 85)

    def _resize(self, content: bytes, max_side: int, quality: int) -> bytes:
        # IMREAD_COLOR applies EXIF orientation, so phone photos show upright.
        image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise InvalidCaptureException("La foto no es una imagen válida.")
        height, width = image.shape[:2]
        scale = min(1.0, max_side / max(height, width))
        if scale < 1.0:
            image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise InvalidCaptureException("No se pudo procesar la foto.")
        return encoded.tobytes()
