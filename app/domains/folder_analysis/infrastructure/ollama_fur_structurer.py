"""
The tax receipt lane's LLM step. Same shape as the folios one (which fills gaps
in the asientos): it talks to Ollama's /api/chat directly, borrowing the
architects' PCs through the digitization contract instead of pinning one host.

It is handed the OCR text, never the photo. qwen3-vl:4b can read an image, but
the receipt has already been read by PaddleOCR by the time this runs: sending
text instead of pixels is what keeps the lane as fast as the folio one, and it
also means the model cannot see -- and so cannot invent -- an amount that is not
in the text the caller checks its answer against.
"""
import json
import re
import time
from contextlib import nullcontext
from typing import Any, Callable, ContextManager, Dict, List, Optional, Sequence

import requests

from app.core.config.settings import settings
from app.domains.folder_analysis.domain.exceptions import (
    TaxStructurerStoppedException,
    TaxStructurerUnavailableException,
)
from app.domains.folder_analysis.domain.ports import TaxStructurerPort
from app.domains.folder_analysis.domain.services.fur_parser import FIELDS

# What each key is called on the form, so the model looks for the printed label
# and not for our English key name. Built from the parser's own labels, plus the
# values that are printed as a whole line instead of next to a label.
_HINTS: Dict[str, str] = {
    **{key: f'el valor rotulado "{labels[0]}"' for key, labels, _kind in FIELDS},
    "receipt_type": 'el tipo de comprobante (ej. "FUR - COMPROBANTE DE PAGO")',
    "receipt_number": "el número del comprobante",
    "municipality": 'el gobierno municipal (ej. "GAM - COCHABAMBA")',
    "concept": 'la línea del concepto del tributo (ej. "INMUEBLES IMPBI 2024 TOTAL")',
    "tax_year": "la gestión (el año) de ese concepto",
    "taxpayer": 'el contribuyente: {"type": natural o jurídica, "id_number": el número de C.I., "name": el nombre}',
}

SYSTEM_PROMPT = """Eres un asistente que ordena el texto OCR de un comprobante de pago de impuestos
municipales de Bolivia (FUR - COMPROBANTE DE PAGO, IMPBI, RUAT). Recibes el texto completo tal como
lo leyó el OCR y la lista de datos que faltan.
Devuelve SOLO un JSON con exactamente las claves pedidas.
Reglas estrictas:
- copia cada valor tal como aparece en el texto: no corrijas, no completes, no reformatees;
- si un dato no está en el texto, usa null: nunca lo deduzcas ni lo inventes;
- los montos van sin "Bs" y con los mismos dígitos y separadores que el texto;
- no agregues claves que no estén en la lista."""

# The PCs belong to the architects: give their VRAM back soon after the call.
KEEP_ALIVE = "2m"

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _json_object(content: str) -> str:
    """The JSON object inside the answer. Asking for `format: json` is usually
    enough, but a reasoning model can still put its thinking around it, and one
    stray word before the brace would throw away a perfectly good reading."""
    match = _JSON_OBJECT.search(content or "")
    return match.group(0) if match is not None else (content or "")


class OllamaFurStructurer(TaxStructurerPort):
    """`host_provider(model)` (the digitization pool, wired in presentation/deps.py)
    returns the PCs that currently have the model, least busy first; each one is
    tried in turn and TAX_RECEIPT_OLLAMA_URL is the last resort, so a single PC
    being off or busy does not stop the pass."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_tokens: Optional[int] = None,
        host_provider: Optional[Callable[[str], List[str]]] = None,
        borrow: Optional[Callable[[str, float], ContextManager[None]]] = None,
    ):
        self._base = (base_url if base_url is not None else settings.TAX_RECEIPT_OLLAMA_URL).rstrip("/")
        # `is not None`, not `or`: an empty model is a choice (the pass off), not a
        # missing argument to fall back on.
        self._model = model if model is not None else settings.TAX_RECEIPT_LLM_MODEL
        self._timeout = timeout or settings.TAX_RECEIPT_LLM_TIMEOUT_SECONDS
        self._max_tokens = max_tokens or settings.TAX_RECEIPT_LLM_MAX_TOKENS
        self._host_provider = host_provider
        # Marks the PC as busy while the call runs, so the monitor screen sees it,
        # and hands back the "Detener" flag that monitor can raise.
        self._borrow = borrow or (lambda _host, _seconds: nullcontext(lambda: False))

    def is_configured(self) -> bool:
        """An empty TAX_RECEIPT_LLM_MODEL turns the pass off: the lane then reads
        with the rules alone, which is the whole reading for a receipt the OCR got
        cleanly, and leaves the rest for the architect to fill in."""
        if not self._model:
            return False
        return bool(self._base) or self._host_provider is not None

    def hosts(self) -> List[str]:
        hosts = list(self._host_provider(self._model)) if self._host_provider else []
        if self._base and self._base not in hosts:
            hosts.append(self._base)
        return hosts

    def structure(self, ocr_text: str, missing: Sequence[str]) -> Dict[str, Any]:
        hosts = self.hosts()
        if not hosts:
            raise TaxStructurerUnavailableException(
                f"Ninguna computadora conectada tiene el modelo {self._model}."
            )
        prompt = self._prompt(ocr_text, missing)
        last_error: Optional[Exception] = None
        for host in hosts:
            try:
                return self._ask(host, prompt)
            except requests.RequestException as exc:
                last_error = exc
        raise TaxStructurerUnavailableException("No se pudo consultar a Ollama.") from last_error

    @staticmethod
    def _prompt(ocr_text: str, missing: Sequence[str]) -> str:
        wanted = "\n".join(f"- {key}: {_HINTS.get(key, key)}" for key in missing)
        return f"Texto OCR del comprobante:\n{ocr_text}\n\nDatos que faltan:\n{wanted}"

    def _ask(self, host: str, prompt: str) -> Dict[str, Any]:
        """Raises requests.RequestException when THIS PC fails (the caller then
        tries the next one). A bad answer is final -- any PC would give the same --
        and so is running out of time: waiting the same budget again on the next PC
        is exactly what this lane must not do."""
        with self._borrow(host, self._timeout) as should_stop:
            response = requests.post(
                f"{host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "format": "json",
                    # Streamed although the JSON is only usable whole: it is what
                    # lets the monitor's "Detener" reach a call already underway.
                    "stream": True,
                    "keep_alive": KEEP_ALIVE,
                    "options": {"temperature": 0, "num_predict": self._max_tokens},
                },
                timeout=self._timeout,
                stream=True,
            )
            with response:
                response.raise_for_status()
                content = self._read(response, should_stop)
        try:
            data = json.loads(_json_object(content))
        except ValueError as exc:
            raise TaxStructurerUnavailableException("Ollama devolvió una respuesta ilegible.") from exc
        if not isinstance(data, dict):
            raise TaxStructurerUnavailableException("Ollama devolvió un JSON inesperado.")
        return data

    def _read(self, response: requests.Response, should_stop: Callable[[], bool]) -> str:
        """Joins the answer as the PC writes it. Leaving this loop closes the
        socket, and Ollama drops the generation as soon as the client hangs up.

        The timeout of the request is per chunk, so a PC that writes slowly but
        steadily would keep the architect waiting for as long as it likes: this
        lane promises seconds, so the whole answer gets one deadline."""
        deadline = time.monotonic() + self._timeout
        parts: List[str] = []
        for line in response.iter_lines(decode_unicode=True):
            if should_stop():
                raise TaxStructurerStoppedException()
            if time.monotonic() > deadline:
                raise TaxStructurerUnavailableException(
                    f"La computadora tardó más de {self._timeout:.0f} s en contestar."
                )
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("error"):
                raise TaxStructurerUnavailableException(f"Ollama falló: {event['error']}")
            parts.append((event.get("message") or {}).get("content") or "")
            if event.get("done"):
                break
        return "".join(parts).strip()
