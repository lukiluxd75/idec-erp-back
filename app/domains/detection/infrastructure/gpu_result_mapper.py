"""
Pure translation helpers between the GPU detection engine's JSON vocabulary
(Spanish, pixel space, ArcGIS ring format) and `detection_results`' vocabulary
(English, WGS84 WKT). No SQLAlchemy or FastAPI here on purpose (see
`sql_processed_sector_repository.py`, which is the only caller) — this module
is verified against a real `GET /jobs/{id}/result` capture, see
doc/ejemplo_resultado_job.json.

Pixel -> geographic conversion: the engine's per-finding `bbox` is in pixel
space (origin top-left) of the single aligned raster described by `img_bbox`
(WGS84 [minLon,minLat,maxLon,maxLat]) + `img_width`/`img_height`. Verified
against the real sample: transforming the centroid of `cambios[0].bbox` this
way reproduces the `lon`/`lat` the engine already reports for that same
finding almost exactly (`-66.155892, -17.39289`), which is what pins down the
row order (y grows downward, so latitude decreases with pixel row).
"""
from __future__ import annotations

from typing import Sequence

# `cambios[].tipo` -> `detection.type` (ck_detection_type).
DETECTION_TYPE_MAP = {
    "nueva": "new",
    "eliminada": "removed",
    "cambio": "changed",
    "sin_cambio": "unchanged",
}

# `cambios[].tipo` -> `affected_parcel.change_type` (ck_affected_parcel_change_type).
AFFECTED_PARCEL_CHANGE_TYPE_MAP = {
    "nueva": "new",
    "eliminada": "removed",
    "cambio": "modified",
    "sin_cambio": "unchanged",
}

# `cruce_predio.confianza` -> `affected_parcel.match_confidence`.
MATCH_CONFIDENCE_MAP = {
    "alta": "high",
    "media": "medium",
    "baja": "low",
}

# `cruce_predio.motivo` (when not "ok") -> `affected_parcel.no_match_reason`.
NO_MATCH_REASON_MAP = {
    "sin_capa": "no_layer",
    "no_layer": "no_layer",
    "fuera_buffer": "outside_buffer",
    "outside_buffer": "outside_buffer",
    "error_arcgis": "arcgis_error",
    "arcgis_error": "arcgis_error",
}
NO_MATCH_REASON_FALLBACK = "arcgis_error"

STAGE_GROUPS: dict[str, set[str]] = {
    "alignment": {"plan", "wms_a", "wms_b", "align"},
    "shadows": {"shadows"},
    "detection": {"detect", "filter", "predios", "done"},
}

ARTIFACT_KIND_MAP = {
    "aligned_a": "aligned_a",
    "aligned_b": "aligned_b",
    "panel_resultado": "result_panel",
    "align_check": "checkerboard",
}
ARTIFACT_KIND_FALLBACK = "other"


def _lonlat_from_pixel(
    px_x: float, px_y: float, img_bbox: Sequence[float], img_width: float, img_height: float
) -> tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = img_bbox
    lon = min_lon + (px_x / img_width) * (max_lon - min_lon)
    lat = max_lat - (px_y / img_height) * (max_lat - min_lat)
    return lon, lat


def _ring_wkt(coords: Sequence[tuple[float, float]]) -> str:
    points = list(coords)
    if points[0] != points[-1]:
        points = points + [points[0]]
    return "(" + ", ".join(f"{lon} {lat}" for lon, lat in points) + ")"


def pixel_bbox_to_wkt_polygon(
    bbox_px: Sequence[float], img_bbox: Sequence[float], img_width: float, img_height: float
) -> str:
    """A finding's pixel bbox [x0,y0,x1,y1] -> WKT POLYGON in EPSG:4326."""
    x0, y0, x1, y1 = bbox_px
    corners_px = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    coords = [_lonlat_from_pixel(px, py, img_bbox, img_width, img_height) for px, py in corners_px]
    return f"POLYGON({_ring_wkt(coords)})"



def geo_bbox_to_wkt_polygon(bbox: Sequence[float]) -> str:
    """A [minLon,minLat,maxLon,maxLat] request bbox -> WKT POLYGON, used for
    `processed_sector.geom` when the job was started with `bbox` (not `polygon`)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    coords = [(min_lon, min_lat), (max_lon, min_lat), (max_lon, max_lat), (min_lon, max_lat)]
    return f"POLYGON({_ring_wkt(coords)})"


def lonlat_ring_to_wkt_polygon(ring: Sequence[Sequence[float]]) -> str:
    """The request's `polygon` ring ([[lon,lat], ...]) -> WKT POLYGON, used for
    `processed_sector.geom` when the job was started with a drawn polygon."""
    coords = [(pt[0], pt[1]) for pt in ring]
    return f"POLYGON({_ring_wkt(coords)})"


def arcgis_rings_to_wkt_multipolygon(rings: Sequence[Sequence[Sequence[float]]]) -> str:
    """`predios.features_geo[].rings` (already WGS84 lon/lat, verified against
    the real sample) -> WKT MULTIPOLYGON for `affected_parcel.parcel_geom`.
    First ring is the exterior, any further rings are holes — ArcGIS winding
    order is not corrected here since every sample seen so far has one ring."""
    rings_wkt = ", ".join(_ring_wkt([(pt[0], pt[1]) for pt in ring]) for ring in rings)
    return f"MULTIPOLYGON(({rings_wkt}))"


def pixel_area_to_m2(area_px: float, gsd_m: float) -> float:
    """Findings report footprint area in pixels^2 (verified: area_ref=1899 px^2
    at gsd~0.104 m/px -> ~20 m^2, consistent with the finding's bbox size)."""
    return area_px * (gsd_m**2)
