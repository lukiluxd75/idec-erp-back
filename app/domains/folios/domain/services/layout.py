"""
Page geometry of a `folio real`, from OCR boxes + ruling lines -- no image
library here (the pixels are handled by PageImagePort; this only reasons about
coordinates).

Why this exists: the OCR service downsizes large images before detecting text,
so on a full page the small typewritten lines of column A get lost (tested on a
real folio: whole lines like the notary's name were missing). Cropping column A
and the header block and OCR-ing each crop on its own reads every line. To crop
we need (1) the page upright and (2) where the columns are:

1. Orientation -- the three column titles "A) TITULARIDAD...", "B) GRAVÁMENES..."
   and "C) CANCELACIONES" sit on one row, left to right, on every page of the
   form. The OCR service reads rotated text fine, so on the raw photo the vector
   A -> C tells how the page is turned; rotating by its angle makes it point
   right (and deskews at the same time, it is not snapped to 90°).
2. Columns -- the form's vertical ruling lines (found by OpenCV) bound column A,
   the narrow PROPORCIÓN column and column B. The titles only say which gap is
   which; if the lines are not found we fall back to the title boxes.
"""
import math
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from app.domains.folios.domain.entities.ocr_block import OcrBlock
from app.domains.folios.domain.services.text import compact, find_label, normalize, similar

Rect = Tuple[int, int, int, int]


def find_containing(blocks: Sequence[OcrBlock], word: str, min_ratio: float = 0.8) -> Optional[OcrBlock]:
    """Block whose compacted text contains `word` (fuzzy: sliding window, to
    survive one wrong letter, e.g. 'GRAVAMENES' read as 'GRAVAMENFS')."""
    target = compact(word)
    best, best_score = None, 0.0
    for b in blocks:
        c = compact(b.text)
        if len(c) < len(target) - 1:
            continue
        if target in c:
            score = 1.0
        else:
            score = max(
                (similar(c[i : i + len(target)], target) for i in range(0, max(1, len(c) - len(target) + 1))),
                default=0.0,
            )
        if score > best_score:
            best, best_score = b, score
    return best if best_score >= min_ratio else None


@dataclass(frozen=True)
class ColumnTitles:
    a: Optional[OcrBlock]
    b: Optional[OcrBlock]
    c: Optional[OcrBlock]


def find_column_titles(blocks: Sequence[OcrBlock]) -> ColumnTitles:
    return ColumnTitles(
        a=find_containing(blocks, "TITULARIDAD"),
        b=find_containing(blocks, "GRAVAMENES"),
        c=find_containing(blocks, "CANCELACIONES"),
    )


def detect_rotation(blocks: Sequence[OcrBlock]) -> Optional[float]:
    """Counter-clockwise angle (degrees) that turns the page upright, or None if
    fewer than two column titles were found (the caller then tries the other
    orientations). Image coordinates have y pointing down, so atan2(dy, dx) of
    the A->C vector is exactly the CCW rotation that brings it to +x."""
    t = find_column_titles(blocks)
    ordered = [x for x in (t.a, t.b, t.c) if x is not None]
    if len(ordered) < 2:
        return None
    dx = ordered[-1].cx - ordered[0].cx
    dy = ordered[-1].cy - ordered[0].cy
    if math.hypot(dx, dy) < 1:
        return None
    angle = math.degrees(math.atan2(dy, dx))
    # Same range as the caller's fallback rotations, and 0 stays 0 (no -0.0).
    return round(((angle + 180) % 360) - 180, 2) or 0.0


def transform_blocks(blocks: Sequence[OcrBlock], matrix) -> List[OcrBlock]:
    """Apply a 2x3 affine matrix (source -> rotated image) to every box and
    keep the axis-aligned bounds of the 4 transformed corners."""
    (a, b, c), (d, e, f) = matrix
    out = []
    for blk in blocks:
        corners = [(blk.x0, blk.y0), (blk.x1, blk.y0), (blk.x1, blk.y1), (blk.x0, blk.y1)]
        xs = [a * x + b * y + c for x, y in corners]
        ys = [d * x + e * y + f for x, y in corners]
        out.append(OcrBlock(blk.text, blk.confidence, min(xs), min(ys), max(xs), max(ys)))
    return out


_PAGE_RE = re.compile(r"PAG(\d{1,2})DE(\d{1,2})")


def find_page_number(blocks: Sequence[OcrBlock]) -> Tuple[Optional[int], Optional[int]]:
    """'Pag 1 de 2' printed at the bottom of every page."""
    for b in blocks:
        m = _PAGE_RE.search(compact(b.text))
        if m:
            number, total = int(m.group(1)), int(m.group(2))
            if 1 <= number <= total <= 50:
                return number, total
    return None, None


_DATE_RE = re.compile(r"^FECHA:?(\d{2}/\d{2}/\d{4})$")


def find_issue_date(blocks: Sequence[OcrBlock]) -> Optional[str]:
    """'Fecha: 06/02/2025' next to the page number -- when the folio was printed.
    Anchored to a block that is ONLY that (column B has 'de fecha dd/mm/yyyy')."""
    for b in blocks:
        m = _DATE_RE.match(normalize(b.text).replace(" ", ""))
        if m:
            return m.group(1)
    return None


@dataclass
class PageLayout:
    width: int
    height: int
    has_header: bool = False
    header_rect: Optional[Rect] = None
    titularidad_rect: Optional[Rect] = None  # column A + PROPORCION
    # x range (page frame) of the PROPORCIÓN column, between A and B.
    proportion_range: Optional[Tuple[float, float]] = None
    page_number: Optional[int] = None
    page_total: Optional[int] = None
    issue_date: Optional[str] = None
    observations: List[str] = field(default_factory=list)


def _clamp_rect(x0: float, y0: float, x1: float, y1: float, w: int, h: int) -> Optional[Rect]:
    r = (max(0, int(x0)), max(0, int(y0)), min(w, int(math.ceil(x1))), min(h, int(math.ceil(y1))))
    return r if r[2] - r[0] > 20 and r[3] - r[1] > 20 else None


def plan_regions(blocks: Sequence[OcrBlock], vertical_lines: Sequence[float], width: int, height: int) -> PageLayout:
    """Where to crop on an upright page. `blocks` are the full-page OCR boxes
    already in the upright frame."""
    layout = PageLayout(width=width, height=height)
    layout.page_number, layout.page_total = find_page_number(blocks)
    layout.issue_date = find_issue_date(blocks)

    titles = find_column_titles(blocks)
    a, b = titles.a, titles.b
    lines = sorted(vertical_lines)

    if a is None:
        layout.observations.append("No se encontró el título de la columna A) en la página.")
    line_h = a.h if a is not None else max(height * 0.012, 10)

    # Column boundaries: nearest ruling lines around the titles.
    left = right_a = prop_right = None
    if a is not None:
        left = max((x for x in lines if x < a.x0), default=None)
        right_a = min((x for x in lines if x > a.x1), default=None)
        if b is not None and right_a is not None and right_a >= b.x0:
            right_a = None  # the "line" is past column B's title: not ours
        if right_a is not None:
            prop_right = min((x for x in lines if x > right_a + line_h), default=None)
            if b is not None and prop_right is not None and prop_right >= b.x0:
                prop_right = None
        if left is None:
            left = max(0.0, a.x0 - a.w * 0.6)
        if right_a is None:
            # Without lines: column A ends a bit after its (centered) title.
            right_a = a.x1 + (a.x0 - left) * 0.9
            if b is not None:
                right_a = min(right_a, b.x0 - line_h)
    if right_a is not None and prop_right is not None:
        layout.proportion_range = (right_a, prop_right)

    # Vertical extent of the columns: below the titles, above "REGISTRADOR:"
    # (bottom band with signature / page number).
    if a is not None:
        title_bottom = max(x.y1 for x in (a, b) if x is not None)
        proportion_title = find_containing(blocks, "CION", min_ratio=1.0)  # 2nd line of "PROPOR-CION"
        if proportion_title is not None and abs(proportion_title.cy - a.cy) < 2 * line_h:
            title_bottom = max(title_bottom, proportion_title.y1)
        footer = find_label(blocks, "REGISTRADOR")
        bottom = footer.y0 if footer is not None and footer.y0 > title_bottom else height
        # The crop includes the narrow PROPORCION column: its '1/1' are as small
        # as column A's text and the full-page OCR misses them too.
        crop_right = prop_right if prop_right is not None else right_a
        layout.titularidad_rect = _clamp_rect(
            left - line_h * 0.2, title_bottom + line_h * 0.3, crop_right - line_h * 0.1, bottom - line_h * 0.2,
            width, height,
        )

    # Header block (page 1 only): from just above "MATRÍCULA N°" to the titles row.
    matricula = find_label(blocks, "MATRICULA")
    if matricula is not None and (a is None or matricula.cy < a.cy):
        layout.has_header = True
        # Rightmost ruling line = the form's right border (if it was found).
        right_border = max(lines) if lines and max(lines) > (b.x1 if b is not None else width * 0.5) else width
        header_bottom = a.y0 - line_h * 0.3 if a is not None else matricula.y1 + height * 0.35
        layout.header_rect = _clamp_rect(
            (left - line_h * 0.2) if left is not None else 0,
            matricula.y0 - matricula.h * 2.5,
            right_border + line_h * 0.2,
            header_bottom,
            width, height,
        )
    return layout
