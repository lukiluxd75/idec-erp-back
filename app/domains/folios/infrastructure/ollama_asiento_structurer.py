import json
from contextlib import nullcontext
from typing import Any, Callable, ContextManager, Dict, List, Optional

import requests

from app.core.config.settings import settings
from app.domains.folios.domain.exceptions import (
    AsientoStructurerStoppedException,
    AsientoStructurerUnavailableException,
)
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


# The PCs belong to the architects: give their VRAM back soon after the call.
KEEP_ALIVE = "2m"


class OllamaAsientoStructurer(AsientoStructurerPort):
    """Talks to Ollama's /api/chat directly instead of importing the chatbot
    domain's engine (no cross-domain imports outside contracts/ -- CLAUDE.md §2).

    `host_provider(model)` (the digitization pool, wired in presentation/deps.py)
    returns the PCs that currently have the model, least busy first; each one is
    tried in turn and FOLIOS_OLLAMA_URL is the last resort, so a single PC being
    off or busy no longer stops the pass."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        host_provider: Optional[Callable[[str], List[str]]] = None,
        borrow: Optional[Callable[[str, float], ContextManager[None]]] = None,
    ):
        self._base = (base_url if base_url is not None else settings.FOLIOS_OLLAMA_URL).rstrip("/")
        self._model = model or settings.FOLIOS_LLM_MODEL
        self._timeout = timeout or settings.FOLIOS_LLM_TIMEOUT_SECONDS
        self._host_provider = host_provider
        self._borrow = borrow or (lambda _host, _seconds: nullcontext(lambda: False))

    def is_configured(self) -> bool:
        return bool(self._base) or self._host_provider is not None

    def hosts(self) -> List[str]:
        hosts = list(self._host_provider(self._model)) if self._host_provider else []
        if self._base and self._base not in hosts:
            hosts.append(self._base)
        return hosts

    def structure(self, raw_text: str) -> Dict[str, Any]:
        hosts = self.hosts()
        if not hosts:
            raise AsientoStructurerUnavailableException(
                f"Ninguna computadora conectada tiene el modelo {self._model}."
            )
        last_error: Optional[Exception] = None
        for host in hosts:
            try:
                return self._ask(host, raw_text)
            except requests.RequestException as exc:
                last_error = exc
        raise AsientoStructurerUnavailableException("No se pudo consultar a Ollama.") from last_error

    def _ask(self, host: str, raw_text: str) -> Dict[str, Any]:
        """Raises requests.RequestException when THIS PC fails (the caller then
        tries the next one); a bad answer is final -- any PC would give the same."""
        with self._borrow(host, self._timeout) as should_stop:
            response = requests.post(
                f"{host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": raw_text},
                    ],
                    "format": "json",
                    # Streamed although the JSON is only usable whole: it is what lets the monitor's "Detener" reach a call already underway.
                    "stream": True,
                    "keep_alive": KEEP_ALIVE,
                    "options": {"temperature": 0},
                },
                timeout=self._timeout,
                stream=True,
            )
            with response:
                response.raise_for_status()
                content = self._read(response, should_stop)
        try:
            data = json.loads(content)
        except ValueError as exc:
            raise AsientoStructurerUnavailableException("Ollama devolvió una respuesta ilegible.") from exc
        if not isinstance(data, dict):
            raise AsientoStructurerUnavailableException("Ollama devolvió un JSON inesperado.")
        return data

    @staticmethod
    def _read(response: requests.Response, should_stop: Callable[[], bool]) -> str:
        """Joins the answer as the PC writes it. Leaving this loop closes the
        socket, and Ollama drops the generation as soon as the client hangs up."""
        parts: List[str] = []
        for line in response.iter_lines(decode_unicode=True):
            if should_stop():
                raise AsientoStructurerStoppedException()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("error"):
                raise AsientoStructurerUnavailableException(f"Ollama falló: {event['error']}")
            parts.append((event.get("message") or {}).get("content") or "")
            if event.get("done"):
                break
        return "".join(parts).strip()
