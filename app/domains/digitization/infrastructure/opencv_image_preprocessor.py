import cv2
import numpy as np

from app.domains.digitization.domain.exceptions import InvalidDocumentException
from app.domains.digitization.domain.ports import ImagePreprocessorPort

_MAX_DESKEW_DEGREES = 10.0
_MIN_DESKEW_DEGREES = 0.5


class OpenCvImagePreprocessor(ImagePreprocessorPort):
    """Shrinks, denoises, boosts contrast and straightens slightly skewed scans.
    Color is kept (stamps, plan colors). Smaller images also mean less VRAM and
    time on the architects' PCs."""

    def __init__(self, max_side: int = 1600, jpeg_quality: int = 90):
        self._max_side = max_side
        self._jpeg_quality = jpeg_quality

    def prepare(self, content: bytes) -> bytes:
        # IMREAD_COLOR applies EXIF orientation, so phone photos come out upright.
        image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise InvalidDocumentException(
                "El archivo no es una imagen válida o su formato no es compatible "
                "(se aceptan JPG, PNG, TIFF, BMP o WEBP)."
            )

        image = self._limit_size(image)
        image = cv2.fastNlMeansDenoisingColored(image, None, 5, 5, 7, 21)
        image = self._enhance_contrast(image)
        image = self._deskew(image)

        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
        if not ok:
            raise InvalidDocumentException("No se pudo procesar la imagen del documento.")
        return encoded.tobytes()

    def _limit_size(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        longest = max(height, width)
        if longest <= self._max_side:
            return image
        scale = self._max_side / longest
        return cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _enhance_contrast(image: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        lightness, a, b = cv2.split(lab)
        lightness = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lightness)
        return cv2.cvtColor(cv2.merge((lightness, a, b)), cv2.COLOR_LAB2BGR)

    @staticmethod
    def _skew_angle(image: np.ndarray) -> float:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        coords = cv2.findNonZero(ink)
        if coords is None or len(coords) < 100:
            return 0.0
        # The reported range differs across OpenCV versions; fold any of them into (-45, 45].
        angle = cv2.minAreaRect(coords)[-1] % 90
        if angle > 45:
            angle -= 90
        return float(angle)

    def _deskew(self, image: np.ndarray) -> np.ndarray:
        angle = self._skew_angle(image)
        # Larger angles are more likely a drawing's layout than a skewed scan.
        if not (_MIN_DESKEW_DEGREES <= abs(angle) <= _MAX_DESKEW_DEGREES):
            return image
        height, width = image.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        return cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
