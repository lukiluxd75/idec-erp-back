"""Small geometry helpers -- WKT in, GeoJSON out. Deliberately not shared
with `detection`'s own gpu_result_mapper.py: this backend avoids cross-domain
imports (see detection/infrastructure/models.py's header), so each domain
owns its own handful of geometry-conversion lines."""
from typing import Any, Dict, Sequence

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping as shapely_to_geojson


def ring_to_wkt_polygon(ring: Sequence[Sequence[float]]) -> str:
    """A [[lon,lat], ...] ring (open or closed) -> a WKT POLYGON, closing it
    if the caller did not repeat the first point."""
    points = list(ring)
    if points[0] != points[-1]:
        points = points + [points[0]]
    coords = ", ".join(f"{lon} {lat}" for lon, lat in points)
    return f"POLYGON(({coords}))"


def geom_to_geojson(geom_wkb) -> Dict[str, Any]:
    return shapely_to_geojson(to_shape(geom_wkb))
