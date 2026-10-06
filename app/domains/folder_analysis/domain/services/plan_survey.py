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
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 00-33-432-012-0-00-000-000 as printed (OCR may swap a dash for a space or dot).
_CODE_PRINTED = re.compile(
    r"(\d{2})\s*[-–.]\s*(\d{2})\s*[-–.]\s*([0-9A-Z]{3})\s*[-–.]\s*(\d{3})\s*[-–.]\s*(\d)\s*[-–.]\s*(\d{2})\s*[-–.]\s*(\d{3})\s*[-–.]\s*(\d{3})", re.IGNORECASE
)
# P1  E 806132.14  N 8063496.75   (the E and N letters are not always read).
_POINT = re.compile(
    r"\bP\s*(\d{1,2})\b[^0-9]{0,8}(\d{6}(?:[.,]\d+)?)[^0-9]{1,10}(\d{7}(?:[.,]\d+)?)", re.IGNORECASE
)
# "SUPERFICIE TOTAL UTIL", as the OCR misreads it ("TTAL").
_SURFACE = re.compile(
    r"SUP(?:ERFICIE|\.)?\s*(?:T[A-Z]{2,4}\s*)?UTIL[^0-9]{0,40}(\d[\d.,]*)\s*M[2²]", re.IGNORECASE
)
# Any surface the sheet writes: "295.31 m2", ".267.55m2".
_ANY_SURFACE = re.compile(r"(?<!\d)(\d{1,5}[.,]\d{2})\s*M[2²]", re.IGNORECASE)
# The corners of a lot can be rounded: "R5.00" is a corner of radius 5 m.
_RADIUS = re.compile(r"(?<![A-Z.])R\s*(\d{1,2}[.,]\d{2})(?!\d)", re.IGNORECASE)
# The table of coordinates when the OCR lost the P labels: an easting and a northing.
_EAST = re.compile(r"(?<![\d.,])(\d{6}[.,]\d{1,3})(?![\d])")
_NORTH = re.compile(r"(?<![\d.,])(\d{7}[.,]\d{1,3})(?![\d])")


def _number(text: str) -> float:
    return float(text.replace(",", "."))


def printed_code(text: str) -> Optional[str]:
    """The code catastral exactly as printed on the plano, with dashes."""
    match = _CODE_PRINTED.search(text or "")
    return "-".join(match.groups()).upper() if match else None


def parse_vertices(text: str) -> List[Dict[str, Any]]:
    """The UTM table of the plano, one entry per vertex, in the order it is
    printed. Each point is kept once: the first reading of a label wins."""
    seen: Dict[int, Dict[str, Any]] = {}
    for match in _POINT.finditer(text or ""):
        number = int(match.group(1))
        if number in seen:
            continue
        seen[number] = {"name": f"P{number}", "east": _number(match.group(2)), "north": _number(match.group(3))}
    if len(seen) >= 3:
        return [seen[number] for number in sorted(seen)]
    return _unlabelled_vertices(text)


def _unlabelled_vertices(text: str) -> List[Dict[str, Any]]:
    """The table when the OCR dropped the P1..Pn column: the eastings and the
    northings, each in the order the text gives them, are paired by position. The
    table closes the polygon by repeating P1, so a last point equal to the first is
    dropped. The OCR sometimes swaps two rows of the table, which makes the polygon
    cross itself: the order is then looked for among the ones that do not cross."""
    easts = [_number(m.group(1)) for m in _EAST.finditer(text or "")]
    norths = [_number(m.group(1)) for m in _NORTH.finditer(text or "")]
    if len(easts) != len(norths) or len(easts) < 3:
        return []
    points = list(zip(easts, norths))
    if len(points) > 3 and points[-1] == points[0]:
        points = points[:-1]
    if len(points) < 3 or len(set(points)) != len(points):
        return []
    points = _simple_order(points)
    return [{"name": f"P{i + 1}", "east": e, "north": n} for i, (e, n) in enumerate(points)]


def _crosses(a, b, c, d) -> bool:
    def side(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def _is_simple(points) -> bool:
    n = len(points)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(i - j) in (1, n - 1):
                continue
            if _crosses(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]):
                return False
    return True


def _simple_order(points):
    """`points` as they are when they already draw a polygon; otherwise the first
    ordering (keeping the first point where it is) that does not cross itself."""
    if _is_simple(points) or len(points) > 7:
        return points
    from itertools import permutations

    for rest in permutations(points[1:]):
        candidate = [points[0], *rest]
        if _is_simple(candidate):
            return candidate
    return points


def declared_surface(text: str) -> Optional[float]:
    """The "superficie total útil" the plano prints, in m2."""
    match = _SURFACE.search(text or "")
    if match:
        try:
            return float(match.group(1).rstrip(".,").replace(",", "."))
        except ValueError:
            pass
    # The OCR often separates the label from its figure.
    counts: Dict[float, int] = {}
    for found in _ANY_SURFACE.finditer(text or ""):
        value = _number(found.group(1))
        counts[value] = counts.get(value, 0) + 1
    repeated = [v for v, n in counts.items() if n >= 2]
    if not repeated:
        return next(iter(counts)) if len(counts) == 1 else None
    return max(repeated, key=lambda v: (counts[v], -v))


def rounded_corners_area(radii: Sequence[float]) -> float:
    """What the rounded corners take from the polygon the vertices draw: a corner of
    radius r cuts (1 - pi/4) * r2 from the square corner."""
    return sum((1 - math.pi / 4) * r * r for r in radii)


def corner_radii(text: str) -> List[float]:
    """The radii (m) of the rounded corners the drawing marks, one per label."""
    return [_number(m.group(1)) for m in _RADIUS.finditer(text or "")]


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


AREA_TOLERANCE = 0.02
AREA_TOLERANCE_MIN_M2 = 1.0
STREET_MAX_DISTANCE_M = 40.0
STREET_TIE_M = 1.0


def _point_to_segment(p: Tuple[float, float], a: Sequence[float], b: Sequence[float]) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(a, b, c, d) -> bool:
    return _cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0


def _distance_to_streets(point: Tuple[float, float], paths: Sequence[Sequence[Sequence[float]]]) -> Optional[float]:
    distances = [
        _point_to_segment(point, a, b) for path in paths for a, b in zip(path, path[1:])
    ]
    return min(distances) if distances else None


def measures(
    reading: Optional[Dict[str, Any]],
    street_paths: Sequence[Sequence[Sequence[float]]],
    declared_area: Optional[float],
    corner_radii: Sequence[float] = (),
) -> Dict[str, Any]:
    """Frente, contra frente and the two fondos of a four-sided plano, computed
    from its UTM vertices once the GIS says which side faces the street.

    Only answers when the numbers can be trusted: the vertices must draw a lot (no
    crossing sides), enclose the surface the plano prints, and one side must
    clearly be the one on the street. Otherwise `values` is empty and `note` says
    why, so the architect types them instead of finding a wrong figure filled in.
    Fondo is the side after the frente in the order of the vertices, Fondo 2 the
    one before it.
    """
    empty: Dict[str, Any] = {"values": {}, "note": None, "area_checked": False}

    def refuse(note: str) -> Dict[str, Any]:
        return {**empty, "note": note}

    if not reading:
        return refuse(
            "El plano no trae tabla de coordenadas: las medidas salen de las cotas del dibujo al analizarlo "
            "y, si no se leyeron ahí, se cargan a mano."
        )
    sides, vertices = reading["sides"], reading["vertices"]
    if len(sides) != 4:
        return refuse(f"El lote del plano tiene {len(sides)} lados: frente y fondos se cargan a mano.")
    points = [(v["east"], v["north"]) for v in vertices]
    if _segments_cross(points[0], points[1], points[2], points[3]) or _segments_cross(
        points[1], points[2], points[3], points[0]
    ):
        return refuse("Las coordenadas del plano se cruzan: revise que estén bien leídas.")
    area_checked = declared_area is not None
    rounded = rounded_corners_area(corner_radii)
    tolerance = max(AREA_TOLERANCE_MIN_M2, (declared_area or 0) * AREA_TOLERANCE)
    if area_checked and min(
        abs(reading["area_m2"] - declared_area), abs(reading["area_m2"] - rounded - declared_area)
    ) > tolerance:
        return refuse(
            f"Las coordenadas dan {reading['area_m2']} m2 y el plano declara {declared_area} m2: "
            "no se calculan los lados, revise las coordenadas."
        )
    middles = [
        ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0) for a, b in zip(points, points[1:] + points[:1])
    ]
    distances = [_distance_to_streets(m, street_paths) for m in middles]
    if any(d is None for d in distances) or min(distances) > STREET_MAX_DISTANCE_M:
        return refuse("El IDE no tiene una calle junto al lote: el frente se carga a mano.")
    ranked = sorted(range(4), key=lambda i: distances[i])
    if distances[ranked[1]] - distances[ranked[0]] < STREET_TIE_M:
        return refuse("El lote da a más de una calle (esquina): el frente se carga a mano.")
    front = ranked[0]

    def length(index: int) -> str:
        return f"{sides[index % 4]['length_m']:.2f} m"

    return {
        "values": {
            "frontage": length(front),
            "rear_frontage": length(front + 2),
            "depth": length(front + 1),
            "depth_2": length(front + 3),
        },
        "note": None,
        "area_checked": area_checked,
    }


def read_plan(text: str) -> Dict[str, Any]:
    """Everything the plano says about its own lot that the lookup can compare."""
    vertices = parse_vertices(text)
    radii = corner_radii(text)
    drawn = survey(vertices)
    if drawn and radii:
        # The vertices draw square corners: the surface of the lot is what is left once the rounded ones are cut.
        drawn["corner_radii"] = radii
        drawn["area_net_m2"] = round(drawn["area_m2"] - rounded_corners_area(radii), 2)
    return {
        "printed_code": printed_code(text),
        "declared_area_m2": declared_surface(text),
        "survey": drawn,
    }
