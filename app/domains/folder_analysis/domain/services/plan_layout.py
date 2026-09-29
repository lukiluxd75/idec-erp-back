"""
Puts the OCR of a plano back together: the text as it is written on the sheet,
the grids as tables, and the labelled values as pairs.

A plano is not a form. A folio and a FUR have a fixed layout, so their parsers
can look for a label and know what belongs next to it; an architectural drawing
has whatever the draughtsman put on it. So nothing here interprets what it
reads -- it only restores the structure the OCR loses (which blocks are one
line, which cells are one row) and leaves the meaning to the architect.

Pure: the blocks arrive through the folios contract and the grid lines from
OpenCV (see infrastructure/opencv_plan_reader.py); this module never touches
either.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.domains.folder_analysis.domain.services.text import (
    Block,
    clean_value,
    group_lines,
    join_text,
    normalize,
)

# Two rules closer than this (as a share of the page height) are the two edges of
# the same printed line, not a row with something written in it.
MIN_ROW_HEIGHT_RATIO = 0.004

# A grid needs at least this many row lines (a top, a bottom and one divider):
# with fewer, what OpenCV found is a wall of the drawing, not a table.
MIN_ROW_LINES = 3
MIN_COLUMN_LINES = 2

# Rules belong to the same table when they run over the same part of the sheet.
# This is what tells a cuadro from the long walls of the drawing: a wall has no
# three parallel neighbours above the same stretch of paper.
MIN_OVERLAP_RATIO = 0.5

# ...and when they are near each other. A row of a cuadro is never this tall.
MAX_ROW_GAP_RATIO = 0.12

# A "NAME: value" longer than this is a sentence that happens to have a colon.
MAX_FIELD_NAME_CHARS = 48


@dataclass(frozen=True)
class Segment:
    """A straight rule OpenCV found on the sheet: where it sits across the page
    (`position`) and the stretch it runs over (`start`..`end`)."""

    position: float
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class TableRegion:
    """One cuadro of the plano: the box it occupies and its row lines."""

    top: float
    bottom: float
    left: float
    right: float
    rows: List[float]


def page_title(blocks: Sequence[Block]) -> str:
    """What the sheet calls itself. The draughtsman writes the planta with the
    biggest lettering on the plano ("PLANTA BAJA", "PLANTA 1° PISO"), so that is
    what is looked for first; failing that, the largest text on the page."""
    titled = [b for b in blocks if normalize(b.text).startswith("PLANTA")]
    if titled:
        return clean_value(max(titled, key=lambda b: b.h).text) or ""
    readable = [b for b in blocks if len(b.text.strip()) >= 3]
    if not readable:
        return ""
    return clean_value(max(readable, key=lambda b: b.h).text) or ""


def page_text(lines: Sequence[Sequence[Block]]) -> str:
    """The page as it reads: one line of text per line on the sheet."""
    return "\n".join(filter(None, (join_text(line) for line in lines)))


def labelled_fields(lines: Sequence[Sequence[Block]]) -> List[Dict[str, str]]:
    """The "ETIQUETA: valor" pairs of the rótulo and the notes -- the only thing
    on a plano that carries its own name. First one wins: a label repeated on
    the sheet (a legend under each drawing) is one value, not several."""
    fields: List[Dict[str, str]] = []
    seen = set()
    for line in lines:
        text = join_text(line)
        if ":" not in text:
            continue
        raw_name, _, raw_value = text.partition(":")
        # A colon between digits is a scale or a time ("ESC 1:100", "14:30"),
        # never a label and its value.
        if raw_name[-1:].isdigit() and raw_value[:1].isdigit():
            continue
        name = clean_value(raw_name)
        value = clean_value(raw_value)
        if not name or not value or len(name) > MAX_FIELD_NAME_CHARS:
            continue
        key = normalize(name)
        if key in seen:
            continue
        seen.add(key)
        fields.append({"name": name, "value": value})
    return fields


def table_regions(rules: Sequence[Segment], page_height: int) -> List[TableRegion]:
    """The cuadros of the sheet, from the horizontal rules OpenCV found.

    A plano is not a photo of a table: its cuadro de superficies may take up a
    corner of the sheet, and the drawing itself is full of long straight strokes
    that look exactly like a rule. What tells them apart is company -- a table is
    several rules, one under the other, over the same stretch of paper -- so that
    is what is grouped on, and not how long each stroke is."""
    ordered = sorted(rules, key=lambda rule: rule.position)
    maximum_gap = page_height * MAX_ROW_GAP_RATIO
    minimum_step = page_height * MIN_ROW_HEIGHT_RATIO

    # Every open cuadro is looked at, not just the last one: a long wall of the
    # drawing sits between the rows of a cuadro on the other side of the sheet,
    # and it must not cut that cuadro in two.
    groups: List[List[Segment]] = []
    for rule in ordered:
        best, best_overlap = None, 0.0
        for group in groups:
            if rule.position - group[-1].position > maximum_gap:
                continue
            overlap = _overlap_ratio(group, rule)
            if overlap >= MIN_OVERLAP_RATIO and overlap > best_overlap:
                best, best_overlap = group, overlap
        if best is None:
            groups.append([rule])
        elif rule.position - best[-1].position >= minimum_step:
            best.append(rule)

    regions = []
    for group in groups:
        if len(group) < MIN_ROW_LINES:
            continue
        regions.append(
            TableRegion(
                top=group[0].position,
                bottom=group[-1].position,
                left=min(rule.start for rule in group),
                right=max(rule.end for rule in group),
                rows=[rule.position for rule in group],
            )
        )
    return regions


def _overlap_ratio(group: Sequence[Segment], rule: Segment) -> float:
    """How much of the shorter of the two runs over the same stretch of paper."""
    left = max(min(r.start for r in group), rule.start)
    right = min(max(r.end for r in group), rule.end)
    shared = right - left
    shortest = min(rule.length, max(r.length for r in group))
    return shared / shortest if shared > 0 and shortest > 0 else 0.0


def table_from_grid(
    blocks: Sequence[Block], row_lines: Sequence[float], column_lines: Sequence[float]
) -> List[List[str]]:
    """The cells of one grid, as rows of text. A block belongs to the cell its
    centre falls in; a row or a column with nothing in it anywhere is dropped,
    because the OCR reads the frame of the sheet as a line too."""
    rows = _merged(row_lines, 1.0)
    columns = _merged(column_lines, 1.0)
    if len(rows) < MIN_ROW_LINES or len(columns) < MIN_COLUMN_LINES:
        return []

    grid: List[List[List[Block]]] = [[[] for _ in columns[:-1]] for _ in rows[:-1]]
    for block in blocks:
        row = _slot(block.cy, rows)
        column = _slot(block.cx, columns)
        if row is not None and column is not None:
            grid[row][column].append(block)

    table = [[join_text(sorted(cell, key=lambda b: b.x0)) for cell in row] for row in grid]
    return _without_empty_rows_and_columns(table)


def read_page(
    blocks: Sequence[Block],
    grids: Sequence[Tuple[TableRegion, Sequence[float]]],
) -> Dict[str, Any]:
    """One page of the plano, in the shape the lane has always stored (the same
    the vision model answered with), so the review screen does not change.

    `grids`: each cuadro found on the sheet with its column lines."""
    lines = group_lines(blocks)
    tables = [table_from_grid(blocks, region.rows, columns) for region, columns in grids]
    return {
        "document_type": page_title(blocks),
        "full_text": page_text(lines),
        "fields": labelled_fields(lines),
        "tables": [table for table in tables if table],
    }


def _merged(positions: Sequence[float], minimum_gap: float) -> List[float]:
    """Sorted positions with the ones closer than `minimum_gap` collapsed."""
    merged: List[float] = []
    for position in sorted(positions):
        if merged and position - merged[-1] < max(minimum_gap, 1.0):
            continue
        merged.append(position)
    return merged


def _slot(position: float, boundaries: Sequence[float]) -> Optional[int]:
    """Which band between consecutive boundaries `position` falls in."""
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        if start <= position < end:
            return index
    return None


def _without_empty_rows_and_columns(table: List[List[str]]) -> List[List[str]]:
    kept_columns = [i for i in range(len(table[0])) if any(row[i].strip() for row in table)]
    rows = [[row[i] for i in kept_columns] for row in table if any(cell.strip() for cell in row)]
    return rows if len(rows) > 1 and len(kept_columns) > 1 else []
