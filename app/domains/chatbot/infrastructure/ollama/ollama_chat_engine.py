import json
from contextlib import nullcontext
from typing import Any, Callable, ContextManager, Dict, List, Optional
from urllib.parse import urljoin

import requests

from app.core.config.settings import settings
from app.domains.chatbot.domain.exceptions import ChatEngineUnavailableException
from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort


class OllamaChatEngine(ChatEnginePort):
    """HTTP adapter to an external Ollama host. Single adapter, no in-process
    fallback: unlike detection's GPU engine, running the LLM inside the ERP
    backend itself is not planned (see the integration plan) -- an unreachable
    or unconfigured host degrades to 503, everything else in the domain keeps
    working."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        chat_model: Optional[str] = None,
        vision_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        chat_timeout: Optional[float] = None,
        vision_timeout: Optional[float] = None,
        embedding_timeout: Optional[float] = None,
        borrow: Optional[Callable[[str, float], ContextManager[None]]] = None,
    ):
        self._base = (base_url if base_url is not None else settings.CHATBOT_OLLAMA_URL).rstrip("/")
        self._chat_model = chat_model or settings.CHATBOT_CHAT_MODEL
        self._vision_model = vision_model or settings.CHATBOT_VISION_MODEL
        self._embedding_model = embedding_model or settings.CHATBOT_EMBEDDING_MODEL
        self._chat_timeout = chat_timeout or settings.CHATBOT_CHAT_TIMEOUT_SECONDS
        self._vision_timeout = vision_timeout or settings.CHATBOT_VISION_TIMEOUT_SECONDS
        self._embedding_timeout = embedding_timeout or settings.CHATBOT_EMBEDDING_TIMEOUT_SECONDS
        self._borrow = borrow or (lambda _host, _seconds: nullcontext(lambda: False))

    def _post(
        self, path: str, payload: Dict[str, Any], timeout: float, stream: bool = False
    ) -> Dict[str, Any]:
        """`stream` asks Ollama to write the answer in fragments and rebuilds it
        here. It changes nothing for the caller, and it is what lets the PC
        monitor's "Detener" reach a call that is already underway."""
        if not self._base:
            raise ChatEngineUnavailableException(
                "El motor de IA (Ollama) todavía no está configurado. Contacte a un administrador."
            )
        url = urljoin(self._base + "/", path.lstrip("/"))
        try:
            with self._borrow(self._base, timeout) as should_stop:
                response = requests.post(
                    url, json={**payload, "stream": stream}, timeout=timeout, stream=stream
                )
                if stream:
                    with response:
                        response.raise_for_status()
                        return self._read_stream(response, should_stop)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise ChatEngineUnavailableException(
                "El motor de IA no respondió a tiempo. Intente de nuevo en unos minutos."
            ) from exc
        except requests.RequestException as exc:
            raise ChatEngineUnavailableException(
                "No se pudo conectar con el motor de IA. Intente de nuevo más tarde."
            ) from exc
        return response.json()

    def chat(self, system_prompt: str, messages: List[Dict[str, str]]) -> str:
        data = self._post(
            "/api/chat",
            {
                "model": self._chat_model,
                "messages": [{"role": "system", "content": system_prompt}, *messages],
            },
            self._chat_timeout,
            stream=True,
        )
        return data.get("message", {}).get("content", "")

    def vision(self, system_prompt: str, user_text: str, image_base64: str) -> str:
        data = self._post(
            "/api/chat",
            {
                "model": self._vision_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text, "images": [image_base64]},
                ],
            },
            self._vision_timeout,
            stream=True,
        )
        return data.get("message", {}).get("content", "")

    def embed(self, text: str) -> List[float]:
        data = self._post(
            "/api/embeddings",
            {"model": self._embedding_model, "prompt": text},
            self._embedding_timeout,
        )
        return data.get("embedding", [])

    def extract_json(self, system_prompt: str, raw_text: str) -> Dict[str, Any]:
        data = self._post(
            "/api/chat",
            {
                "model": self._chat_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_text},
                ],
                "format": "json",
            },
            self._chat_timeout,
            stream=True,
        )
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise ChatEngineUnavailableException("El motor de IA devolvió una respuesta vacía.")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ChatEngineUnavailableException(
                "El motor de IA devolvió una respuesta que no se pudo interpretar."
            ) from exc

    @staticmethod
    def _read_stream(response: requests.Response, should_stop: Callable[[], bool]) -> Dict[str, Any]:
        """Puts the fragments back together into the answer shape the callers
        already expect. Leaving this loop closes the socket, and Ollama drops the
        generation as soon as the client hangs up."""
        parts: List[str] = []
        for line in response.iter_lines(decode_unicode=True):
            if should_stop():
                raise ChatEngineUnavailableException(
                    "La consulta se detuvo desde el monitor de computadoras."
                )
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("error"):
                raise ChatEngineUnavailableException(f"El motor de IA falló: {event['error']}")
            parts.append((event.get("message") or {}).get("content") or "")
            if event.get("done"):
                break
        return {"message": {"content": "".join(parts)}}
