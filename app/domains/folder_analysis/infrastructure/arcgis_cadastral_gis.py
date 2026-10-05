"""
The cadastral GIS of the municipality (the IDE), read through the ArcGIS REST
services it publishes -- the same ones the "croquis de certificado" demo draws
from. Read-only: the ERP only asks which predio a code is, who is next to it and
which streets pass by.

Only the geoserver's own host is ever called (settings.CADASTRAL_GIS_URL).
"""
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from app.core.config.settings import settings
from app.domains.folder_analysis.domain.exceptions import CadastralGisUnavailableException
from app.domains.folder_analysis.domain.ports.cadastral_gis_port import CadastralGisPort, GisParcel
from app.domains.folder_analysis.domain.services.parcel_geometry import Neighbour, Ring, Street

logger = logging.getLogger("uvicorn.error")

PARCELS_LAYER = "catastro/prediosCertificado1/MapServer/0"
STREETS_LAYER = "catastro/viasCertificado/MapServer/0"
USE_LAYER = "catastro/usoSueloCertificado/MapServer/0"
BLOCKS_LAYER = "catastro/manzanasCertificado/MapServer/0"
# The services the croquis is stacked from, bottom to top (the same order the certificate demo adds them in).
CROQUIS_SERVICES = ("usoSueloCertificado", "manzanasCertificado", "prediosCertificado1", "viasCertificado")
# WGS84 / UTM zone 19 south: what the layers are stored in and what the plano's coordinate table is printed in.
UTM_19S = 32719


class ArcGisCadastralGis(CadastralGisPort):
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None, session: Any = None):
        self._base = (base_url or settings.CADASTRAL_GIS_URL).rstrip("/")
        self._timeout = timeout or settings.CADASTRAL_GIS_TIMEOUT_SECONDS
        self._http = session or requests

    def find_parcel(self, gis_code: str) -> Optional[GisParcel]:
        features = self._query(
            PARCELS_LAYER, {"where": f"CodCat = '{gis_code.replace(chr(39), chr(39) * 2)}'"}
        )
        for feature in features:
            ring = _outer_ring(feature.get("geometry"))
            if ring:
                return GisParcel(code=gis_code, ring=ring, attributes=feature.get("attributes") or {})
        return None

    def parcels_around(self, ring: Ring, distance_m: float) -> List[Neighbour]:
        features = self._query(PARCELS_LAYER, self._around(ring, distance_m))
        found: List[Neighbour] = []
        for feature in features:
            outline = _outer_ring(feature.get("geometry"))
            attributes = feature.get("attributes") or {}
            if outline:
                found.append(
                    Neighbour(
                        code=str(attributes.get("CodCat") or ""),
                        number=str(attributes.get("Nro_predio") or "").strip().lstrip("0") or "",
                        ring=outline,
                    )
                )
        return found

    def streets_around(self, ring: Ring, distance_m: float) -> Sequence[Street]:
        features = self._query(STREETS_LAYER, self._around(ring, distance_m))
        streets: List[Street] = []
        for feature in features:
            attributes = feature.get("attributes") or {}
            paths = (feature.get("geometry") or {}).get("paths") or []
            if not paths:
                continue
            name = str(attributes.get("Nombre") or attributes.get("Nombre_V") or "").strip()
            streets.append(
                Street(
                    kind=str(attributes.get("Tipo") or "Calle").strip(),
                    name=name,
                    paths=paths,
                    key=str(attributes.get("OBJECTID") or ""),
                )
            )
        return streets

    def land_use_at(self, point: Tuple[float, float]) -> Dict[str, Any]:
        features = self._query(USE_LAYER, {**self._at(point), "returnGeometry": "false"})
        return dict(features[0].get("attributes") or {}) if features else {}

    def block_at(self, point: Tuple[float, float]) -> Dict[str, Any]:
        features = self._query(BLOCKS_LAYER, {**self._at(point), "returnGeometry": "false"})
        return dict(features[0].get("attributes") or {}) if features else {}

    def map_image(
        self, layer: str, bbox: Tuple[float, float, float, float], size: int, transparent: bool
    ) -> bytes:
        if layer not in CROQUIS_SERVICES:
            raise CadastralGisUnavailableException("Capa del GIS no permitida.")
        params = {
            "f": "image",
            "size": f"{size},{size}",
            "bbox": ",".join(str(v) for v in bbox),
            "bboxSR": UTM_19S,
            "format": "png",
            "transparent": "true" if transparent else "false",
        }
        url = f"{self._base}/arcgis/rest/services/catastro/{layer}/MapServer/export"
        try:
            response = self._http.get(url, params=params, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Folder analysis: el GIS catastral no dio la imagen (%s): %s", layer, exc)
            raise CadastralGisUnavailableException(
                "No se pudo obtener el mapa del GIS catastral. Intente de nuevo."
            ) from exc
        return response.content

    @staticmethod
    def _at(point: Tuple[float, float]) -> Dict[str, Any]:
        return {
            "geometry": f"{point[0]},{point[1]}",
            "geometryType": "esriGeometryPoint",
            "inSR": UTM_19S,
            "spatialRel": "esriSpatialRelIntersects",
        }

    @staticmethod
    def _around(ring: Ring, distance_m: float) -> Dict[str, Any]:
        import json

        return {
            "geometry": json.dumps({"rings": [[list(p) for p in ring]], "spatialReference": {"wkid": UTM_19S}}),
            "geometryType": "esriGeometryPolygon",
            "inSR": UTM_19S,
            "spatialRel": "esriSpatialRelIntersects",
            "distance": distance_m,
            "units": "esriSRUnit_Meter",
        }

    def _query(self, layer: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        body = {"outFields": "*", "returnGeometry": "true", "outSR": UTM_19S, "f": "json", **params}
        url = f"{self._base}/arcgis/rest/services/{layer}/query"
        try:
            # POST: a polygon with many vertices does not fit in a URL.
            response = self._http.post(url, data=body, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Folder analysis: el GIS catastral no respondió (%s): %s", layer, exc)
            raise CadastralGisUnavailableException(
                "No se pudo consultar el GIS catastral. Revise la conexión e intente de nuevo."
            ) from exc
        if isinstance(payload, dict) and payload.get("error"):
            logger.warning("Folder analysis: el GIS catastral devolvió un error (%s): %s", layer, payload["error"])
            raise CadastralGisUnavailableException("El GIS catastral rechazó la consulta.")
        return list(payload.get("features") or [])


def _outer_ring(geometry: Optional[Dict[str, Any]]) -> Optional[Ring]:
    """The outline of the predio: the biggest ring the geometry has."""
    rings = (geometry or {}).get("rings") or []
    rings = [r for r in rings if len(r) >= 4]
    if not rings:
        return None

    def area(r: Ring) -> float:
        return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(r, r[1:] + r[:1]))) / 2.0

    return max(rings, key=area)
