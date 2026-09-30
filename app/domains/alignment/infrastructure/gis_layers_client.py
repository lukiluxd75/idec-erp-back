"""Thin client for the GIS orthophoto WMS layer catalog (years available,
their ArcGIS service names, and the candidate GIS hosts). This is generic
catastro infrastructure, not detection business logic -- it happens to be
exposed on the same server as the detection engine (settings.DETECTION_ENGINE_URL),
so this duplicates GpuDetectionClient.list_wms_layers() as its own small,
independent call rather than importing the `detection` domain."""
import re
from typing import Any

import requests

from app.core.config.settings import settings

# Same hosts the frontend already hardcodes (see AlignmentMap.jsx's
# GIS_HOSTS) -- validated here too since get_wms_image() takes `host` as a
# client-supplied parameter and proxies a real HTTP request to it (SSRF
# guard: only ever fetch from a GIS host we know about).
_ALLOWED_HOSTS = {
    "https://gs.catastrocbba.com",
    "http://192.168.105.219:6080",
    "http://172.16.67.110:6080",
}
_SERVICE_RE = re.compile(r"^[A-Za-z0-9_]+$")


class GisLayersUnavailable(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def list_wms_layers() -> dict[str, Any]:
    url = f"{settings.DETECTION_ENGINE_URL.rstrip('/')}/api/v1/wms/layers"
    try:
        response = requests.get(url, timeout=settings.DETECTION_ENGINE_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GisLayersUnavailable(f"No se pudo obtener el catálogo de capas WMS: {exc}") from exc
    data = response.json()
    return data if isinstance(data, dict) else {"layers": [], "hosts": []}


def fetch_wms_image(
    host: str,
    service: str,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> bytes:
    """Raw WMS GetMap PNG bytes for a bbox -- the "before" (un-corrected)
    imagery AlignmentPage warps client-side onto a block's fitted transform
    (see the module's design: the correction itself stays a browser-side
    canvas operation, this just proxies the source pixels around CORS)."""
    if host not in _ALLOWED_HOSTS:
        raise GisLayersUnavailable(f"Host GIS no permitido: {host}")
    if not _SERVICE_RE.match(service):
        raise GisLayersUnavailable("Nombre de servicio WMS inválido.")
    width = min(max(int(width), 64), 2048)
    height = min(max(int(height), 64), 2048)
    url = f"{host}/arcgis/services/imagenes/{service}/MapServer/WMSServer"
    params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": "0",
        "styles": "",
        "crs": "CRS:84",
        "bbox": ",".join(str(v) for v in bbox),
        "width": width,
        "height": height,
        "format": "image/png",
        "transparent": "false",
    }
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GisLayersUnavailable(f"No se pudo obtener la imagen WMS: {exc}") from exc
    return response.content
