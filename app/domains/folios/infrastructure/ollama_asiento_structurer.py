import json
from typing import Any, Dict, Optional

import requests

from app.core.config.settings import settings
from app.domains.folios.domain.exceptions import AsientoStructurerUnavailableException
from app.domains.folios.domain.ports.asiento_structurer_port import AsientoStructurerPort

SYSTEM_PROMPT = """Eres un asistente que estructura asientos de la columna "A) TITULARIDAD SOBRE EL DOMINIO"
de un folio real de Derechos Reales de Bolivia. Recibes el texto OCR de UN asiento.
Devuelve SOLO un JSON con esta forma exacta:
{"personas": [{"nombre": str, "estado_civil": str|null, "ci": str|null, "expedido": str|null}],
 "acto": str|null, "documento": str|null, "autoridad": str|null}
Reglas: copia los valores tal como aparecen en el texto (no corrijas nombres, no inventes datos);
si un dato no está en el texto, usa null; "acto" es el tipo de transferencia (ej. "Compra Venta");
"documento" es la línea del documento (ej. "Escrit. Priv. de fecha 12/10/1992");
"autoridad" es el notario/juez que lo otorgó."""


class OllamaAsientoStructurer(AsientoStructurerPort):
    """Talks to Ollama's /api/chat directly instead of importing the chatbot
    domain's engine (no cross-domain imports outside contracts/ -- CLAUDE.md §2).
    Its own FOLIOS_OLLAMA_URL, so enabling it here does not depend on the
    chatbot being set up, and vice versa."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None, timeout: Optional[float] = None):
        self._base = (base_url if base_url is not None else settings.FOLIOS_OLLAMA_URL).rstrip("/")
        self._model = model or settings.FOLIOS_LLM_MODEL
        self._timeout = timeout or settings.FOLIOS_LLM_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self._base)

    def structure(self, raw_text: str) -> Dict[str, Any]:
        if not self._base:
            raise AsientoStructurerUnavailableException("Ollama no está configurado para folios.")
        try:
            response = requests.post(
                f"{self._base}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": raw_text},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            content = (response.json().get("message") or {}).get("content", "").strip()
            data = json.loads(content)
        except requests.RequestException as exc:
            raise AsientoStructurerUnavailableException("No se pudo consultar a Ollama.") from exc
        except ValueError as exc:
            raise AsientoStructurerUnavailableException("Ollama devolvió una respuesta ilegible.") from exc
        if not isinstance(data, dict):
            raise AsientoStructurerUnavailableException("Ollama devolvió un JSON inesperado.")
        return data
