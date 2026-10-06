"""
What a predio looks like from the street: who is on each side of it, which streets
it faces and how much land it has -- all measured on the GIS geometry.

The sheet of a carpeta de poseedores asks for the colindancias by cardinal point,
and a lot is not always square to the north, so the sides are named with the eight
points of the compass (N, NE, E, SE, S, SO, O, NO): the direction a side FACES,
which is the direction of its outward normal, and not the way it runs.

Everything here is plain geometry on UTM coordinates (metres), with no network and
no database, so it is tested with the real ring of a predio (CLAUDE.md §3).
"""
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient

Ring = Sequence[Sequence[float]]

# The eight points, clockwise from the north, in the office's spelling (Sud/Oeste).
POINTS = ("Norte", "Noreste", "Este", "Sudeste", "Sud", "Sudoeste", "Oeste", "Noroeste")
POINT_ABBREVIATIONS = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")

SHARED_TOLERANCE_M = 0.8
MIN_SHARED_RATIO = 0.3
STREET_REACH_M = 30.0
# Streets within this of the predio are listed as the ones it faces.
NEAR_STREET_M = 25.0
# Edges shorter than this are digitizing noise.
MIN_EDGE_M = 0.05
MAX_TURN_DEG = 45.0

UNNAMED_STREET = "calle innominada"
# A lot on the corner of two streets: "calle X esquina calle Y".
CORNER = "esquina"
NO_NEIGHBOUR = "sin colindante en el GIS"

KIND_PARCEL = "predio"
KIND_STREET = "via"
KIND_NONE = "none"


@dataclass(frozen=True)
class Neighbour:
    """Another predio of the cadastre."""

    code: str
    number: str
    ring: Ring


@dataclass(frozen=True)
class Street:
    """A street of the cadastre: its axis, which can come in several pieces."""

    kind: str
    name: str
    paths: Sequence[Ring]
    # Which street this axis belongs to.
    key: str = ""

    @property
    def label(self) -> str:
        name = (self.name or "").strip()
        if not name:
            return UNNAMED_STREET
        kind = (self.kind or "Calle").strip().lower()
        return f"{kind} {name}"


@dataclass
class Side:
    """One side of the predio: a run of edges that face the same neighbour."""

    index: int
    start: Tuple[float, float]
    end: Tuple[float, float]
    length_m: float
    azimuth: float
    point: str
    abbreviation: str
    kind: str
    name: str
    code: Optional[str] = None
    distance_m: Optional[float] = None
    street_key: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "start": list(self.start),
            "end": list(self.end),
            "length_m": round(self.length_m, 2),
            "azimuth": round(self.azimuth, 1),
            "point": self.point,
            "abbreviation": self.abbreviation,
            "kind": self.kind,
            "name": self.name,
            "code": self.code,
            "distance_m": None if self.distance_m is None else round(self.distance_m, 1),
            "street_key": self.street_key,
        }


def compass_point(azimuth: float) -> Tuple[str, str]:
    """The point of the compass an azimuth (degrees from the north, clockwise) is
    closest to. Each one owns the 45 degrees centred on it."""
    index = int(((azimuth % 360.0) + 22.5) // 45.0) % 8
    return POINTS[index], POINT_ABBREVIATIONS[index]


def polygon_of(ring: Ring) -> Polygon:
    """The predio as a polygon, counter-clockwise so that the outward normal of an
    edge is always to its right."""
    polygon = Polygon([(p[0], p[1]) for p in ring])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda part: part.area)
    return orient(polygon, sign=1.0)


def _azimuth(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _outward_azimuth(start: Sequence[float], end: Sequence[float]) -> float:
    """Where the edge faces. With the ring counter-clockwise the outside is to the
    right of the direction of travel."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    return _azimuth(dy, -dx)


@dataclass
class _Edge:
    start: Tuple[float, float]
    end: Tuple[float, float]
    length: float
    facing: float
    kind: str = KIND_NONE
    key: str = ""
    name: str = NO_NEIGHBOUR
    code: Optional[str] = None
    distance: Optional[float] = None
    street_key: Optional[str] = None


def _edges(polygon: Polygon) -> List[_Edge]:
    coords = list(polygon.exterior.coords)
    edges: List[_Edge] = []
    for a, b in zip(coords, coords[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < MIN_EDGE_M:
            continue
        edges.append(_Edge((a[0], a[1]), (b[0], b[1]), length, _outward_azimuth(a, b)))
    return edges


def _neighbour_of(edge: _Edge, neighbours: Sequence[Tuple[Neighbour, Polygon]]) -> Optional[Tuple[Neighbour, float]]:
    line = LineString([edge.start, edge.end])
    zone = line.buffer(SHARED_TOLERANCE_M)
    best: Optional[Tuple[Neighbour, float]] = None
    for neighbour, polygon in neighbours:
        if polygon.distance(line) > SHARED_TOLERANCE_M:
            continue
        shared = polygon.boundary.intersection(zone).length
        ratio = shared / edge.length if edge.length else 0.0
        if ratio >= MIN_SHARED_RATIO and (best is None or ratio > best[1]):
            best = (neighbour, ratio)
    return best


def _street_of(edge: _Edge, streets: Sequence[Tuple[Street, List[LineString]]]) -> Optional[Tuple[Street, float]]:
    middle = Point((edge.start[0] + edge.end[0]) / 2.0, (edge.start[1] + edge.end[1]) / 2.0)
    facing = math.radians(edge.facing)
    normal = (math.sin(facing), math.cos(facing))
    best: Optional[Tuple[Street, float]] = None
    for street, lines in streets:
        for line in lines:
            distance = line.distance(middle)
            if distance > STREET_REACH_M:
                continue
            nearest = line.interpolate(line.project(middle))
            toward = (nearest.x - middle.x, nearest.y - middle.y)
            # The street has to be on the side the edge faces, or the back of a lot would be given the street of its front.
            if toward[0] * normal[0] + toward[1] * normal[1] <= 0:
                continue
            if best is None or distance < best[1]:
                best = (street, distance)
    return best


def _turn(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _sides(edges: List[_Edge]) -> List[Side]:
    if not edges:
        return []
    # Start the walk where the colindante changes, so a run that crosses the first vertex of the ring is not cut in two.
    cut = next((i for i in range(len(edges)) if edges[i].key != edges[i - 1].key), 0)
    edges = edges[cut:] + edges[:cut]

    groups: List[List[_Edge]] = []
    for edge in edges:
        if (
            groups
            and groups[-1][-1].key == edge.key
            and _turn(groups[-1][0].facing, edge.facing) <= MAX_TURN_DEG
        ):
            groups[-1].append(edge)
        else:
            groups.append([edge])

    sides: List[Side] = []
    for number, group in enumerate(groups, start=1):
        start, end = group[0].start, group[-1].end
        chord = math.hypot(end[0] - start[0], end[1] - start[1])
        facing = _outward_azimuth(start, end) if chord > MIN_EDGE_M else group[0].facing
        point, abbreviation = compass_point(facing)
        first = group[0]
        sides.append(
            Side(
                index=number,
                start=start,
                end=end,
                length_m=sum(e.length for e in group),
                azimuth=facing,
                point=point,
                abbreviation=abbreviation,
                kind=first.kind,
                name=first.name,
                code=first.code,
                distance_m=first.distance,
                street_key=first.street_key,
            )
        )
    return sides


def boundaries_text(sides: Sequence[Side]) -> str:
    """The colindancias as the sheet writes them: "Norte: lote 5; Sud: calle
    innominada". A point with several colindantes lists them all, in the order the
    sides come, and a side with nobody on it says so instead of being left out."""
    by_point: Dict[str, List[str]] = {}
    for side in sides:
        names = by_point.setdefault(side.point, [])
        label = _side_label(side)
        if label not in names:
            names.append(label)
    return "; ".join(f"{point}: {', '.join(by_point[point])}" for point in POINTS if point in by_point)


def _side_label(side: Side) -> str:
    if side.kind == KIND_PARCEL:
        return f"lote {side.name}"
    return side.name


@dataclass
class ParcelAnalysis:
    """What the GIS says about one predio."""

    area_m2: float
    perimeter_m: float
    sides: List[Side]
    streets: List[Dict[str, Any]] = field(default_factory=list)
    boundaries: str = ""
    street_text: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "area_m2": round(self.area_m2, 2),
            "perimeter_m": round(self.perimeter_m, 2),
            "sides": [side.as_dict() for side in self.sides],
            "streets": self.streets,
            "boundaries": self.boundaries,
            "street_text": self.street_text,
        }


def analyze_parcel(
    parcel: Ring,
    own_code: str,
    neighbours: Sequence[Neighbour],
    streets: Sequence[Street],
) -> ParcelAnalysis:
    polygon = polygon_of(parcel)
    others = [(n, polygon_of(n.ring)) for n in neighbours if n.code != own_code and len(n.ring) >= 4]
    lines = [(s, [LineString([(p[0], p[1]) for p in path]) for path in s.paths if len(path) >= 2]) for s in streets]

    edges = _edges(polygon)
    for edge in edges:
        neighbour = _neighbour_of(edge, others)
        if neighbour is not None:
            found, _ratio = neighbour
            edge.kind, edge.key, edge.code = KIND_PARCEL, f"p:{found.code}", found.code
            edge.name = found.number or found.code
            continue
        street = _street_of(edge, lines)
        if street is not None:
            found_street, distance = street
            street_key = found_street.key or found_street.label
            edge.kind, edge.key, edge.distance = KIND_STREET, f"v:{street_key}", distance
            edge.name, edge.street_key = found_street.label, street_key
            continue
        edge.key = "none"

    sides = _sides(edges)
    near = _near_streets(polygon, lines)
    return ParcelAnalysis(
        area_m2=polygon.area,
        perimeter_m=polygon.length,
        sides=sides,
        streets=near,
        boundaries=boundaries_text(sides),
        street_text=_street_text(sides, near),
    )


def _near_streets(polygon: Polygon, lines: Sequence[Tuple[Street, List[LineString]]]) -> List[Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    for street, parts in lines:
        distances = [part.distance(polygon) for part in parts]
        if not distances or min(distances) > NEAR_STREET_M:
            continue
        key = street.key or street.label
        distance = min(distances)
        if key not in found or distance < found[key]["distance_m"]:
            found[key] = {
                "name": street.label,
                "named": bool((street.name or "").strip()),
                "distance_m": round(distance, 1),
            }
    return sorted(found.values(), key=lambda item: item["distance_m"])


def _street_text(sides: Sequence[Side], near: Sequence[Dict[str, Any]]) -> str:
    """The street the predio fronts. The streets its sides actually face come
    first; failing that, the closest one. An axis with no name is the office's
    "calle innominada"."""
    # One entry per street, not per name: two unnamed streets are a corner.
    faced: Dict[str, str] = {}
    for side in sides:
        if side.kind == KIND_STREET and side.street_key not in faced:
            faced[side.street_key] = side.name
    if faced:
        return f" {CORNER} ".join(faced.values())
    return near[0]["name"] if near else ""
