"""
The OpenCV half of reading a plano: straighten the sheet and find the lines of
its grids, so the OCR blocks can be put back into rows and cells.

Port of `resolutions/utils/tableLineDetector.js`, which does this in the browser
for the Resoluciones P.H. screen and was tuned against real photos. Two things
are kept from it on purpose, because they were learned the hard way there:

  - only rotation is corrected, never perspective. Finding the four corners of a
    table is fragile: a weak edge (glare, a shadow) turns an inner line into the
    border and the crop loses whole columns. Rotating into a larger canvas can
    only fail to improve; it can never lose data.
  - before the long erosion that isolates the rules, the mask is dilated a
    couple of pixels across: without it a slightly tilted line breaks into
    fragments and almost every row line is lost.

What is new here: the vertical lines (the browser only needed rows, its columns
came from the surfaces parser), a guard against absurd angles, and rules that
carry the stretch of paper they run over -- on a plano the cuadro is a corner of
the sheet, not the whole photo, so where a rule runs matters more than how long
it is (see plan_layout.table_regions).
"""
import logging
import math
import statistics
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from app.domains.folder_analysis.domain.services.plan_layout import Segment, TableRegion

logger = logging.getLogger("uvicorn.error")

# A tilt beyond this is not a crooked photo, it is a misdetection (the long
# diagonal of a drawing read as a rule). Better to leave the page as it came.
MAX_SKEW_DEGREES = 10.0

# A rule is long: at least this share of the page across, to be one of the lines
# the page is squared against. Only the sheet's own long rules square a page.
SKEW_LINE_RATIO = 0.4
# A row of a cuadro, on the other hand, can be short -- the cuadro de superficies
# often takes up a corner. What makes it a table is the company it keeps, not its
# length, so this only keeps the noise out.
GRID_LINE_RATIO = 0.08
MIN_GRID_LINE_PX = 60
# A column line only has to cross its own cuadro, top to bottom.
COLUMN_LINE_RATIO = 0.7

JPEG_QUALITY = 90


@dataclass
class DeskewedPage:
    """The page as it was OCR'd: `image` is what was sent to the OCR service, so
    the blocks that come back are in `frame`'s coordinates."""

    image: bytes
    frame: np.ndarray
    angle: float
    corrected: bool


def deskew(content: bytes) -> DeskewedPage:
    """Squares the page against its own horizontal rules. A page with nothing
    that looks like a rule comes back untouched -- a plano with no grid is
    perfectly normal."""
    page = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if page is None:
        raise ValueError("La página no es una imagen legible.")

    angle, found = _skew_angle(page)
    if found < 2 or abs(angle) > MAX_SKEW_DEGREES or abs(angle) < 0.1:
        return DeskewedPage(image=content, frame=page, angle=0.0, corrected=False)

    rotated = _rotate_without_cropping(page, angle)
    ok, encoded = cv2.imencode(".jpg", rotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        return DeskewedPage(image=content, frame=page, angle=0.0, corrected=False)
    return DeskewedPage(image=encoded.tobytes(), frame=rotated, angle=angle, corrected=True)


def column_lines(frame: np.ndarray, region: TableRegion) -> List[float]:
    """The column lines of one cuadro, looked for inside that cuadro alone: two
    tables on the same sheet rarely share their columns, and the drawing around
    them is full of verticals that are not columns of anything."""
    y0, y1 = max(0, int(region.top) - 2), min(frame.shape[0], int(region.bottom) + 2)
    x0, x1 = max(0, int(region.left) - 2), min(frame.shape[1], int(region.right) + 2)
    if y1 - y0 < 8 or x1 - x0 < 8:
        return []
    inside = frame[y0:y1, x0:x1]
    return [x0 + rule.position for rule in _rules(inside, horizontal=False, ratio=COLUMN_LINE_RATIO)]


def row_rules(frame: np.ndarray) -> List[Segment]:
    """Every horizontal rule of the sheet, with the stretch it runs over."""
    return _rules(frame, horizontal=True, ratio=GRID_LINE_RATIO)


def fit_to(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """The page in the frame the OCR answered in, so the lines and the blocks
    can be compared at all (`read_page_text` normalizes what it is given)."""
    if frame.shape[1] == width and frame.shape[0] == height:
        return frame
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def _binarize(frame: np.ndarray) -> np.ndarray:
    # Otsu: separates ink from paper without a fixed threshold -- the light in a
    # phone photo of a plano is never twice the same.
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def _long_strokes(binary: np.ndarray, horizontal: bool) -> np.ndarray:
    """Only the long strokes survive: text is too short for the kernel."""
    span = binary.shape[1] if horizontal else binary.shape[0]
    length = max(15, round(span / 20))
    pre = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3) if horizontal else (3, 1))
    dilated = cv2.dilate(binary, pre)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1) if horizontal else (1, length))
    return cv2.morphologyEx(dilated, cv2.MORPH_OPEN, kernel)


def _contours(mask: np.ndarray) -> Sequence[np.ndarray]:
    found = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    return found[0] if len(found) == 2 else found[1]


def _skew_angle(frame: np.ndarray) -> Tuple[float, int]:
    """The median angle of the page's long horizontal rules -- the median so one
    diagonal of the drawing cannot drag the correction with it."""
    mask = _long_strokes(_binarize(frame), horizontal=True)
    minimum_width = frame.shape[1] * SKEW_LINE_RATIO
    angles = []
    for contour in _contours(mask):
        _, _, width, _ = cv2.boundingRect(contour)
        if width < minimum_width:
            continue
        vx, vy = cv2.fitLine(contour, cv2.DIST_L2, 0, 0.01, 0.01).ravel()[:2]
        angles.append(math.degrees(math.atan2(float(vy), float(vx))))
    if len(angles) < 2:
        return 0.0, len(angles)
    return statistics.median(angles), len(angles)


def _rotate_without_cropping(frame: np.ndarray, angle: float) -> np.ndarray:
    height, width = frame.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    radians = math.radians(abs(angle))
    new_width = round(width * math.cos(radians) + height * math.sin(radians))
    new_height = round(width * math.sin(radians) + height * math.cos(radians))
    matrix[0, 2] += (new_width - width) / 2
    matrix[1, 2] += (new_height - height) / 2
    return cv2.warpAffine(
        frame,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _rules(frame: np.ndarray, horizontal: bool, ratio: float) -> List[Segment]:
    """Every long stroke, as where it sits and the stretch it covers."""
    mask = _long_strokes(_binarize(frame), horizontal=horizontal)
    span = frame.shape[1] if horizontal else frame.shape[0]
    minimum = max(span * ratio, MIN_GRID_LINE_PX if horizontal else 8)
    rules = []
    for contour in _contours(mask):
        x, y, width, height = cv2.boundingRect(contour)
        if horizontal and width >= minimum:
            rules.append(Segment(position=y + height / 2, start=float(x), end=float(x + width)))
        elif not horizontal and height >= minimum:
            rules.append(Segment(position=x + width / 2, start=float(y), end=float(y + height)))
    return sorted(rules, key=lambda rule: rule.position)


def safe_deskew(content: bytes, page_number: int) -> Optional[DeskewedPage]:
    """`deskew` for the pipeline: a page OpenCV cannot handle is not worth losing
    the whole reading over -- it is read as it came."""
    try:
        return deskew(content)
    except Exception:
        logger.exception("Folder analysis: no se pudo enderezar la página %d del plano", page_number)
        return None
