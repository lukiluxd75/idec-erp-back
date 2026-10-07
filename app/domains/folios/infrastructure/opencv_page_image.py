from typing import List, Tuple

import cv2
import numpy as np

from app.domains.folios.domain.exceptions import InvalidFolioUploadException
from app.domains.folios.domain.ports.page_image_port import PageImagePort, Rect, RotatedImage

MAX_SIDE = 3500
JPEG_QUALITY = 95

# angle (CCW, degrees) -> (cv2.rotate code, source->rotated matrix builder for a w x h source).
_QUARTER_TURNS = {
    90: (cv2.ROTATE_90_COUNTERCLOCKWISE, lambda w, h: ((0.0, 1.0, 0.0), (-1.0, 0.0, float(w - 1)))),
    270: (cv2.ROTATE_90_CLOCKWISE, lambda w, h: ((0.0, -1.0, float(h - 1)), (1.0, 0.0, 0.0))),
    180: (cv2.ROTATE_180, lambda w, h: ((-1.0, 0.0, float(w - 1)), (0.0, -1.0, float(h - 1)))),
}


def _decode(content: bytes) -> np.ndarray:
    # IMREAD_COLOR honors EXIF orientation (phone photos).
    img = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise InvalidFolioUploadException("Una de las páginas no es una imagen válida.")
    return img


def _encode(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise InvalidFolioUploadException("No se pudo codificar la imagen de la página.")
    return buf.tobytes()


class OpenCvPageImage(PageImagePort):
    def normalize(self, content: bytes) -> Tuple[bytes, int, int]:
        img = _decode(content)
        h, w = img.shape[:2]
        scale = MAX_SIDE / max(h, w)
        if scale < 1:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]
        return _encode(img), w, h

    def rotate(self, content: bytes, angle_ccw_deg: float) -> RotatedImage:
        img = _decode(content)
        h, w = img.shape[:2]
        quarter = _QUARTER_TURNS.get(round(angle_ccw_deg, 6) % 360)
        if quarter is not None:
            # Exact quarter turn: pixels are moved, not interpolated (no blur).
            code, matrix_for = quarter
            out = cv2.rotate(img, code)
            return RotatedImage(content=_encode(out), width=out.shape[1], height=out.shape[0], matrix=matrix_for(w, h))
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle_ccw_deg, 1.0)
        cos, sin = abs(m[0, 0]), abs(m[0, 1])
        new_w, new_h = int(round(h * sin + w * cos)), int(round(h * cos + w * sin))
        # Shift so the enlarged canvas keeps the whole page (no corner cut off).
        m[0, 2] += new_w / 2 - w / 2
        m[1, 2] += new_h / 2 - h / 2
        out = cv2.warpAffine(
            img, m, (new_w, new_h), flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255),
        )
        matrix = (tuple(float(v) for v in m[0]), tuple(float(v) for v in m[1]))
        return RotatedImage(content=_encode(out), width=new_w, height=new_h, matrix=matrix)

    def vertical_lines(self, content: bytes) -> List[float]:
        """Adaptive threshold (uneven lighting on phone photos) -> morphological
        opening with a tall thin kernel keeps only long vertical strokes -> column
        profile; runs of columns above 15% of the page height are ruling lines.
        Tested on the two sample pages: finds exactly the 5 lines of the A /
        PROPORCIÓN / B / C table."""
        gray = cv2.cvtColor(_decode(content), cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
        h, w = binary.shape
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(h // 12, 10)))
        mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        profile = mask.sum(axis=0) / 255
        columns = np.where(profile > h * 0.15)[0]

        lines: List[float] = []
        run: List[int] = []
        for x in columns:
            if run and x - run[-1] > 6:
                lines.append(float(np.mean(run)))
                run = []
            run.append(int(x))
        if run:
            lines.append(float(np.mean(run)))
        return lines

    def crop(self, content: bytes, rect: Rect) -> bytes:
        img = _decode(content)
        h, w = img.shape[:2]
        x0, y0, x1, y1 = rect
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        return _encode(img[y0:y1, x0:x1])
