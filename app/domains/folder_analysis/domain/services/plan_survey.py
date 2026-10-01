"""
What a poseedores plano says about its own lot, read from the OCR text of the
sheet: the code catastral printed on it, the table of UTM coordinates of its
vertices (P1, P2...) and the surface it declares.

The coordinates are what makes the comparison with the GIS worth doing: the plano
is drawn by the architect and the GIS is the cadastre, and a regularization plano
is exactly the case where the two can differ. With the vertices, the sides and the
area of the plano are computed instead of guessed from the dimension lines, and
the same numbers can be put next to the ones measured on the GIS geometry.

Pure: it only touches the text it is given (CLAUDE.md §3).
"""
import math
import re
from typing import Any, Dict, List, Optional, Tuple

# 00-33-432-012-0-00-000-000 as printed (OCR may swap a dash for a space or dot).
_CODE_PRINTED = re.compile(
    r"(\d{2})\s*[-–.]\s*(\d{2})\s*[-–.]\s*(\d{3})\s*[-–.]\s*(\d{3})\s*[-–.]\s*(\d)\s*[-–.]\s*(\d{2})\s*[-–.]\s*(\d{3})\s*[-–.]\s*(\d{3})"
)
# P1  E 806132.14  N 8063496.75   (the E and N letters are not always read).
_POINT = re.compile(
    r"\bP\s*(\d{1,2})\b[^0-9]{0,8}(\d{6}(?:[.,]\d+)?)[^0-9]{1,10}(\d{7}(?:[.,]\d+)?)", re.IGNORECASE
)
# "SUPERFICIE TOTAL UTIL", as the OCR misreads it ("TTAL").
_SURFACE = re.compile(
    r"SUP(?:ERFICIE|\.)?\s*(?:T[A-Z]{2,4}\s+)?UTIL[^0-9]{0,40}(\d[\d.,]*)", re.IGNORECASE
)


def _number(text: str) -> float:
    return float(text.replace(",", "."))


def printed_code(text: str) -> Optional[str]:
    """The code catastral exactly as printed on the plano, with dashes."""
    match = _CODE_PRINTED.search(text or "")
    return "-".join(match.groups()) if match else None


def parse_vertices(text: str) -> List[Dict[str, Any]]:
    """The UTM table of the plano, one entry per vertex, in the order it is
    printed. Each point is kept once: the first reading of a label wins."""
    seen: Dict[int, Dict[str, Any]] = {}
    for match in _POINT.finditer(text or ""):
        number = int(match.group(1))
        if number in seen:
            continue
        seen[number] = {"name": f"P{number}", "east": _number(match.group(2)), "north": _number(match.group(3))}
    return [seen[number] for number in sorted(seen)]


def declared_surface(text: str) -> Optional[float]:
    """The "superficie total útil" the plano prints, in m2."""
    match = _SURFACE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).rstrip(".,").replace(",", "."))
    except ValueError:
        return None


def survey(vertices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Sides and area of the polygon the vertices draw, in the order printed.
    Fewer than three vertices draw nothing."""
    if len(vertices) < 3:
        return None
    points: List[Tuple[float, float]] = [(v["east"], v["north"]) for v in vertices]
    sides = []
    for index, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
        sides.append(
            {
                "from": vertices[index]["name"],
                "to": vertices[(index + 1) % len(vertices)]["name"],
                "length_m": round(math.hypot(b[0] - a[0], b[1] - a[1]), 2),
            }
        )
    twice_area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))
    return {"vertices": vertices, "sides": sides, "area_m2": round(abs(twice_area) / 2.0, 2)}


def read_plan(text: str) -> Dict[str, Any]:
    """Everything the plano says about its own lot that the lookup can compare."""
    vertices = parse_vertices(text)
    return {
        "printed_code": printed_code(text),
        "declared_area_m2": declared_surface(text),
        "survey": survey(vertices),
    }
