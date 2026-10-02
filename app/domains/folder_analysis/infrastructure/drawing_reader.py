"""
The dimension lines and the street label of the drawing of a poseedores plano
without a table of coordinates (domain/services/drawing_sides.py says what is done
with them).

The whole-page reading is poor at them: the measures along the sides are small,
written at any angle and often over the hatching, so the OCR drops some ("10.11m")
or garbles them ("9.96m" came back as "u966"). Reading only the drawing -- the part
of the sheet above the cuadros -- twice, once as it is and once turned a quarter,
gets every one of them: what runs up and down in the page runs across in the turned
copy, which is the orientation the OCR reads best.

Two more OCR calls per sheet, so it is only done for a sheet that has no UTM table
(a sheet with one has its sides computed and does not need them).
"""
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from app.domains.folder_analysis.domain.services import drawing_sides
from app.domains.folder_analysis.domain.services.text import normalize

logger = logging.getLogger("uvicorn.error")

# What the cuadros of the sheet start with: the drawing is everything above them.
_CARTOUCHE_ANCHORS = ("REGULARIZACION", "POSEEDORES", "RELACION DE SUPERFICIE", "CODIGO CATASTRAL")
# Room left above the first anchor so the cut does not slice a label.
_CUT_MARGIN = 10
# A measure read in both copies is one measure: same value, centres this close
# (in label heights).
_SAME_LABEL = 1.5


def drawing_height(blocks: Sequence[Any]) -> Optional[int]:
    """Where the drawing ends: just above the first cuadro of the sheet, or None
    when the sheet has none we can recognise."""
    tops = [
        b.y0 for b in blocks if normalize(b.text).startswith(_CARTOUCHE_ANCHORS)
    ]
    if not tops:
        return None
    cut = int(min(tops)) - _CUT_MARGIN
    return cut if cut > 100 else None


class DrawingReader:
    """`read_page` is the same OCR call the sheet was read with (injected so the
    lane stays testable without the service)."""

    def __init__(self, read_page: Callable[..., Any]):
        self._read_page = read_page

    def read(self, frame: np.ndarray, blocks: Sequence[Any]) -> Dict[str, Any]:
        """{"dimensions": [{value, x, y, w, h}], "street": {...}|None} in the
        frame of `frame` (the page as the OCR answered it)."""
        cut = drawing_height(blocks)
        if cut is None:
            return {"dimensions": [], "street": None}
        crop = frame[: min(cut, frame.shape[0]), :]
        found: List[Dict[str, float]] = []
        street: Optional[Dict[str, Any]] = None
        for rotated in (False, True):
            try:
                labels, street_found = self._pass(crop, rotated)
            except Exception:
                logger.exception("Folder analysis: no se pudo leer el dibujo del plano")
                continue
            for label in labels:
                if not self._already(found, label):
                    found.append(label)
            street = street or street_found
        # The street may also be on the whole-page reading (it is not always in the crop).
        for block in blocks:
            width = drawing_sides.parse_street(block.text)
            if street is None and width is not None and block.y1 <= cut + _CUT_MARGIN:
                street = self._box(block.x0, block.y0, block.x1, block.y1, width, block.text)
        return {"dimensions": found, "street": street}

    def _pass(self, crop: np.ndarray, rotated: bool) -> Tuple[List[Dict[str, float]], Optional[Dict[str, Any]]]:
        image = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE) if rotated else crop
        ok, encoded = cv2.imencode(".jpg", image)
        if not ok:
            return [], None
        page = self._read_page(encoded.tobytes(), "plano_dibujo.jpg")
        # The OCR may have resized what it was given: back to the pixels of `image`.
        sx, sy = image.shape[1] / max(page.width, 1), image.shape[0] / max(page.height, 1)
        crop_w = crop.shape[1]
        labels: List[Dict[str, float]] = []
        street: Optional[Dict[str, Any]] = None
        for block in page.blocks:
            x0, y0, x1, y1 = block.x0 * sx, block.y0 * sy, block.x1 * sx, block.y1 * sy
            if rotated:
                # (x', y') of the turned copy is (crop_w - y', x') of the crop.
                x0, y0, x1, y1 = crop_w - y1, x0, crop_w - y0, x1
            value = drawing_sides.parse_dimension(block.text)
            if value is not None and block.confidence >= 0.5:
                labels.append(self._label(value, x0, y0, x1, y1))
                continue
            width = drawing_sides.parse_street(block.text)
            if width is not None and street is None:
                street = self._box(x0, y0, x1, y1, width, block.text)
        return labels, street

    @staticmethod
    def _label(value: float, x0: float, y0: float, x1: float, y1: float) -> Dict[str, float]:
        return {"value": value, "x": round((x0 + x1) / 2), "y": round((y0 + y1) / 2), "w": round(x1 - x0), "h": round(y1 - y0)}

    @staticmethod
    def _box(x0: float, y0: float, x1: float, y1: float, width: float, text: str) -> Dict[str, Any]:
        return {
            "width_m": width,
            "text": text,
            "x": round((x0 + x1) / 2),
            "y": round((y0 + y1) / 2),
            "w": round(x1 - x0),
            "h": round(y1 - y0),
        }

    @staticmethod
    def _already(found: Sequence[Dict[str, float]], label: Dict[str, float]) -> bool:
        reach = _SAME_LABEL * max(label["w"], label["h"])
        return any(
            f["value"] == label["value"]
            and abs(f["x"] - label["x"]) <= reach
            and abs(f["y"] - label["y"]) <= reach
            for f in found
        )
