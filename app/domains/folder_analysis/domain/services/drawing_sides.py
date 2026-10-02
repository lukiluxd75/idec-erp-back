"""
The sides of a poseedores plano that has no table of UTM coordinates, read from
the dimension lines the architect wrote on the drawing ("29.61m", "10.11m").

The first format of the plano carries its vertices (plan_survey.py), so its sides
are computed. The second one does not: the lot is drawn with one measure written
along each side, a street label ("CALLE DE 10.00 mts.") on the side that faces it,
and sometimes a diagonal measure inside the lot that is not a side at all. What
tells them apart is where each label sits:

  * the label closest to the street label, on the axis the street runs along, is
    the frente, and the one at the other end of that axis is the contra frente;
  * the labels along the other axis are the fondos, and when there are more than
    two the ones in the middle are interior measures and are left out.

It only answers when the figures hang together: the lot they draw must come out
within a few percent of the surface the plano declares. Otherwise `values` is empty
and `note` says why, so the architect types them instead of finding a wrong figure
filled in (the same rule as plan_survey.measures()).

Pure: it only touches the labels it is given (CLAUDE.md §3).
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.domains.folder_analysis.domain.services.text import normalize

# "29.61m", "9.96m:", "10,11 m": a number with two decimals and its unit, nothing
# else. "295.31 m2" is a surface, not a side, and "30.18m SUP." is not a label.
_DIMENSION = re.compile(r"^\W*(\d{1,3})\s*[.,]\s*(\d{2})\s*M\W*$")
# "CALLE DE 10.00 mts.", "AVENIDA DE 12 MTS", "PASAJE 6.00 mts".
_STREET = re.compile(r"(?:CALLE|AVENIDA|AV|PASAJE|PJE)\.?\s*(?:DE)?\s*(\d{1,3}(?:\s*[.,]\s*\d{1,2})?)\s*(?:MTS?|M)\b")

# A label counts as running up and down (or across) when its box is clearly longer
# one way than the other; a squarish box says nothing about the side it measures.
ORIENTATION_RATIO = 1.3
# The lot drawn by the labels must come out within this share of the declared surface.
AREA_TOLERANCE = 0.15
# The two ends of an axis must be this far apart (in label heights) to be two sides.
MIN_SEPARATION = 2.0


@dataclass(frozen=True)
class Dimension:
    value: float
    cx: float
    cy: float
    w: float
    h: float

    @property
    def vertical(self) -> bool:
        return self.h > self.w * ORIENTATION_RATIO

    @property
    def horizontal(self) -> bool:
        return self.w > self.h * ORIENTATION_RATIO


def parse_dimension(text: str) -> Optional[float]:
    """The metres a label says, or None when it is anything but a measure."""
    match = _DIMENSION.match(normalize(text or ""))
    return float(f"{match.group(1)}.{match.group(2)}") if match else None


def parse_street(text: str) -> Optional[float]:
    """The width a street label says, in metres."""
    match = _STREET.search(normalize(text or ""))
    if not match:
        return None
    try:
        return float(re.sub(r"\s+", "", match.group(1)).replace(",", "."))
    except ValueError:
        return None


def _dimensions(raw: Sequence[Dict[str, Any]]) -> List[Dimension]:
    found: List[Dimension] = []
    for item in raw or []:
        try:
            found.append(
                Dimension(float(item["value"]), float(item["x"]), float(item["y"]), float(item["w"]), float(item["h"]))
            )
        except (KeyError, TypeError, ValueError):
            continue
    return found


def _fmt(value: float) -> str:
    return f"{value:.2f} m"


def assign(
    raw_dimensions: Sequence[Dict[str, Any]],
    street: Optional[Dict[str, Any]],
    declared_area: Optional[float],
) -> Dict[str, Any]:
    """Frente, contra frente and fondos from the labels of the drawing.

    `raw_dimensions`: [{value, x, y, w, h}], the centre and size of each label in
    the page. `street`: {x, y, w, h} of the street label, if the sheet has one.
    Returns {"values": {...}, "note": str|None}.
    """
    empty: Dict[str, Any] = {"values": {}, "note": None}

    def refuse(note: str) -> Dict[str, Any]:
        return {**empty, "note": note}

    labels = _dimensions(raw_dimensions)
    if len(labels) < 3:
        return refuse("El dibujo del plano no tiene suficientes medidas legibles: frente y fondos se cargan a mano.")
    if not street:
        return refuse("No se encontró la calle en el dibujo: no se sabe cuál lado es el frente.")

    sw, sh = float(street.get("w", 0)), float(street.get("h", 0))
    if sw <= 0 or sh <= 0 or max(sw, sh) < min(sw, sh) * ORIENTATION_RATIO:
        return refuse("No se pudo saber hacia dónde corre la calle del dibujo: el frente se carga a mano.")
    street_vertical = sh > sw
    scx, scy = float(street["x"]), float(street["y"])

    # The street runs along one axis: the frente is a label written along that axis.
    along = [d for d in labels if (d.vertical if street_vertical else d.horizontal)]
    across = [d for d in labels if (d.horizontal if street_vertical else d.vertical)]
    if not along:
        return refuse("Ninguna medida del dibujo corre junto a la calle: el frente se carga a mano.")

    def distance(d: Dimension) -> float:
        return abs(d.cx - scx) if street_vertical else abs(d.cy - scy)

    ordered = sorted(along, key=distance)
    frente = ordered[0]
    if len(ordered) > 1 and distance(ordered[1]) - distance(frente) < min(frente.w, frente.h):
        return refuse("El lote da a más de una calle (esquina): el frente se carga a mano.")
    # The contra frente is at the other end of the axis, never the frente itself.
    contra = ordered[-1] if len(ordered) > 1 else None
    if contra is not None:
        gap = abs(distance(contra) - distance(frente))
        if gap < MIN_SEPARATION * min(frente.w, frente.h):
            contra = None

    # The fondos are the labels along the other axis, at its two ends; the ones in
    # between measure something inside the lot (a diagonal) and are not sides.
    if len(across) < 2:
        return refuse("El dibujo no trae las dos medidas de fondo: se cargan a mano.")
    key = (lambda d: d.cy) if street_vertical else (lambda d: d.cx)
    ends = sorted(across, key=key)
    first, second = ends[0], ends[-1]
    if abs(key(second) - key(first)) < MIN_SEPARATION * min(first.w, first.h):
        return refuse("Las medidas de fondo del dibujo están demasiado juntas para ser lados distintos.")

    # The lot they draw has to be the one the plano declares.
    mean_front = (frente.value + (contra.value if contra else frente.value)) / 2.0
    mean_depth = (first.value + second.value) / 2.0
    if declared_area:
        drawn = mean_front * mean_depth
        if abs(drawn - declared_area) > declared_area * AREA_TOLERANCE:
            return refuse(
                f"Las medidas del dibujo dan unos {drawn:.0f} m2 y el plano declara {declared_area:.2f} m2: "
                "no se asignan los lados, revise las medidas."
            )

    values = {
        "frontage": _fmt(frente.value),
        "depth": _fmt(first.value),
        "depth_2": _fmt(second.value),
    }
    if contra is not None:
        values["rear_frontage"] = _fmt(contra.value)
    note = None
    if contra is None:
        note = "No se leyó la medida del contra frente en el dibujo: se carga a mano."
    elif len(across) > 2:
        note = "Se dejó fuera una medida interior del dibujo (una diagonal) que no es un lado."
    return {"values": values, "note": note}
