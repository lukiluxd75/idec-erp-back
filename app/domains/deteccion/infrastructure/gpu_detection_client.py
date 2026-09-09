from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

import requests

from app.core.config.settings import settings
from app.domains.deteccion.domain.exceptions import DetectionEngineError, DetectionEngineUnavailable
from app.domains.deteccion.domain.ports.detection_engine_port import DetectionEnginePort, EngineBinary

_URL_KEYS = {"url", "urls", "href", "src"}
_PATH_RE = re.compile(r"^/(outputs|api)/", re.IGNORECASE)


class GpuDetectionClient(DetectionEnginePort):
    """HTTP adapter to the GPU detection API (stays on 10.0.0.30)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        public_proxy_prefix: str = "/api/deteccion/motor",
    ):
        self._base = (base_url or settings.DETECTION_ENGINE_URL).rstrip("/")
        self._api_key = api_key if api_key is not None else settings.DETECTION_ENGINE_API_KEY
        self._timeout = timeout_seconds or settings.DETECTION_ENGINE_TIMEOUT_SECONDS
        self._public_proxy_prefix = public_proxy_prefix.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        return headers

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = urljoin(self._base + "/", path.lstrip("/"))
        try:
            response = requests.request(
                method,
                url,
                headers={**self._headers(), **kwargs.pop("headers", {})},
                timeout=kwargs.pop("timeout", self._timeout),
                **kwargs,
            )
        except requests.RequestException as exc:
            raise DetectionEngineUnavailable(f"Cannot reach detection engine: {exc}") from exc

        if response.status_code >= 400:
            detail: Any
            try:
                detail = response.json()
            except Exception:
                detail = response.text[:500] or response.reason
            raise DetectionEngineError(
                detail if isinstance(detail, str) else str(detail),
                status_code=response.status_code if response.status_code < 500 else 502,
            )

        if not response.content:
            return {}
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        return response.content

    def health(self) -> dict[str, Any]:
        data = self._request("GET", "/health")
        return data if isinstance(data, dict) else {"raw": data}

    def list_wms_layers(self) -> dict[str, Any]:
        data = self._request("GET", "/api/v1/wms/layers")
        return data if isinstance(data, dict) else {"layers": []}

    def start_detect_wms_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/api/v1/detect-changes-wms-async", json=payload)
        return self.rewrite_urls(data if isinstance(data, dict) else {})

    def get_progress(self, job_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/api/v1/jobs/{job_id}/progress")
        return self.rewrite_urls(data if isinstance(data, dict) else {})

    def get_result(self, job_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/api/v1/jobs/{job_id}/result", timeout=max(self._timeout, 180))
        return self.rewrite_urls(data if isinstance(data, dict) else {})

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        data = self._request("POST", f"/api/v1/jobs/{job_id}/cancel", json={})
        return data if isinstance(data, dict) else {}

    def get_align_manual(self, job_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/api/v1/jobs/{job_id}/align-manual")
        return self.rewrite_urls(data if isinstance(data, dict) else {})

    def preview_align_manual(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", f"/api/v1/jobs/{job_id}/align-manual/preview", json=payload)
        return self.rewrite_urls(data if isinstance(data, dict) else {})

    def apply_align_manual(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", f"/api/v1/jobs/{job_id}/align-manual/apply", json=payload)
        return self.rewrite_urls(data if isinstance(data, dict) else {})

    def get_registro_catastral(self, id_registro: int) -> dict[str, Any]:
        data = self._request("GET", f"/api/v1/catastro/registro-catastral/{id_registro}")
        return data if isinstance(data, dict) else {}

    def fetch_path(self, relative_path: str) -> EngineBinary:
        clean = relative_path.lstrip("/")
        url = urljoin(self._base + "/", clean)
        try:
            response = requests.get(url, headers=self._headers(), timeout=self._timeout, stream=True)
        except requests.RequestException as exc:
            raise DetectionEngineUnavailable(f"Cannot fetch engine asset: {exc}") from exc
        if response.status_code >= 400:
            raise DetectionEngineError(f"Engine asset not found: {clean}", status_code=response.status_code)
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        filename = clean.rsplit("/", 1)[-1]
        return EngineBinary(content=response.content, content_type=content_type, filename=filename)

    def rewrite_urls(self, payload: Any) -> Any:
        """Rewrite absolute/relative engine URLs so the browser hits the ERP proxy."""
        if isinstance(payload, dict):
            out = {}
            for key, value in payload.items():
                if isinstance(value, str) and self._looks_like_engine_url(value):
                    out[key] = self._to_proxy_url(value)
                else:
                    out[key] = self.rewrite_urls(value)
            return out
        if isinstance(payload, list):
            return [self.rewrite_urls(item) for item in payload]
        return payload

    def _looks_like_engine_url(self, value: str) -> bool:
        if value.startswith(self._base):
            return True
        if _PATH_RE.match(value):
            return True
        return False

    def _to_proxy_url(self, value: str) -> str:
        if value.startswith(self._base):
            path = value[len(self._base) :]
        else:
            path = value
        path = "/" + path.lstrip("/")
        return f"{self._public_proxy_prefix}{path}"
