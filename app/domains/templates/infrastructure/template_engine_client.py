import requests
from typing import Any, Dict
from urllib.parse import urljoin

from app.core.config import settings
from app.domains.templates.domain.exceptions import (
    TemplateEngineUnavailableException,
    TemplateEngineErrorException,
)
from app.domains.templates.domain.ports.template_engine_port import TemplateEnginePort

class HttpTemplateEngineClient(TemplateEnginePort):
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        # We assume TEMPLATE_ENGINE_API_URL and TEMPLATE_ENGINE_TIMEOUT_SECONDS in settings
        self._base = base_url if base_url is not None else getattr(settings, "TEMPLATE_ENGINE_API_URL", None)
        self._timeout = timeout or getattr(settings, "TEMPLATE_ENGINE_TIMEOUT_SECONDS", 30.0)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        api_key = getattr(settings, "TEMPLATE_ENGINE_API_KEY", None)
        if api_key:
            headers["X-Api-Key"] = api_key
        return headers

    def _post_data(self, endpoint: str, html_content: str, variables: Dict[str, Any]) -> str:
        if not self._base:
            raise TemplateEngineUnavailableException("Motor de plantillas externo no está configurado.")
        
        url = urljoin(self._base + "/", endpoint)
        payload = {
            "html": html_content,
            "variables": variables
        }
        
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=self._timeout)
        except requests.Timeout as exc:
            raise TemplateEngineUnavailableException("Motor de plantillas externo no respondió a tiempo.") from exc
        except requests.RequestException as exc:
            raise TemplateEngineUnavailableException(f"No se pudo conectar con el Motor de Plantillas Externo: {exc}") from exc

        if response.status_code >= 400:
            raise TemplateEngineErrorException(response.text[:500] or response.reason)
            
        data = response.json()
        return data.get("rendered_html", "")

    def render_template(self, html_content: str, variables: Dict[str, Any]) -> str:
        return self._post_data("api/v1/render", html_content, variables)

    def preview_template(self, html_content: str, variables: Dict[str, Any]) -> str:
        return self._post_data("api/v1/preview", html_content, variables)
