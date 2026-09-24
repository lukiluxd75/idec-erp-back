import base64
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import requests

from app.domains.digitization.domain.entities import WorkerStatus
from app.domains.digitization.domain.exceptions import (
    JobStoppedException,
    WorkerOutputException,
    WorkerTimeoutException,
    WorkerUnavailableException,
)
from app.domains.digitization.domain.ports import VisionWorkerPort

SYSTEM_PROMPT = (
    "You digitize scanned municipal cadastre documents and architectural paperwork. "
    "Transcribe exactly what is written, keeping the original language (usually Spanish), "
    "spelling, numbers and units. Never invent or complete missing data: if something is "
    "illegible, write [ilegible]. Answer only with the requested JSON."
)

USER_PROMPT = (
    "Digitize this document. Return: document_type (short description of what the document is), "
    "full_text (the complete transcription, preserving line breaks), fields (every labeled value "
    "you can read, such as names, ID numbers, cadastral codes, addresses, surfaces, dates and "
    "amounts, as name/value pairs using the label written on the document) and tables (each table "
    "as a list of rows, each row a list of cell texts)."
)

GENERIC_TEMPLATE: Dict[str, Any] = {
    "document_type": "",
    "full_text": "",
    "fields": [{"name": "", "value": ""}],
    "tables": [[["cell"]]],
}

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _answer_format(template: Dict[str, Any]) -> str:
    # The prompt carries the shape instead of Ollama's `format`: with the reasoning
    # model a strict schema makes it loop ("token repeat limit reached").
    return (
        "Answer with ONLY one JSON object, no explanations, with exactly these keys "
        "(use null for values that are not on the document; lists may have any length):\n"
        + json.dumps(template, ensure_ascii=False, indent=1)
    )


def parse_json_answer(content: str) -> Dict[str, Any]:
    cleaned = _THINK_BLOCK.sub("", content or "")
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise WorkerOutputException("la respuesta no contiene JSON")
    try:
        data = json.loads(cleaned[start : end + 1])
    except ValueError as exc:
        raise WorkerOutputException(f"respuesta no es JSON válido ({exc})") from exc
    if not isinstance(data, dict):
        raise WorkerOutputException("la respuesta no es un objeto JSON")
    return data


class OllamaVisionWorker(VisionWorkerPort):
    def __init__(
        self,
        model: str,
        keep_alive: str,
        connect_timeout: float,
        request_timeout: float,
        health_timeout: float,
        num_ctx: int = 20480,
        num_predict: int = 16000,
    ):
        self._model = model
        self._keep_alive = keep_alive
        self._timeout = (connect_timeout, request_timeout)
        self._request_timeout = request_timeout
        self._health_timeout = health_timeout
        self._num_ctx = num_ctx
        self._num_predict = num_predict

    def models(self, host: str) -> Optional[Set[str]]:
        try:
            response = requests.get(f"{host}/api/tags", timeout=self._health_timeout)
            response.raise_for_status()
            models = response.json().get("models", [])
        except (requests.RequestException, ValueError, AttributeError):
            return None
        return {m.get("name") for m in models if isinstance(m, dict)} | {
            m.get("model") for m in models if isinstance(m, dict)
        }

    def check(self, host: str) -> WorkerStatus:
        names = self.models(host)
        if names is None:
            return WorkerStatus(host=host, reachable=False, model_available=False)
        wanted = {self._model, f"{self._model}:latest"}
        return WorkerStatus(host=host, reachable=True, model_available=bool(names & wanted))

    def extract(
        self,
        host: str,
        image: bytes,
        instructions: Optional[str] = None,
        output_template: Optional[Dict[str, Any]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        if instructions:
            prompt = f"{instructions}\n\n{_answer_format(output_template or {})}"
        else:
            prompt = f"{USER_PROMPT}\n\n{_answer_format(GENERIC_TEMPLATE)}"
        payload = {
            "model": self._model,
            # Streamed on purpose, although the answer is only usable whole: it is
            # the one way to let go of a run half way through (Ollama drops the
            # generation as soon as the client hangs up) and to hold the whole job
            # to `request_timeout`, which otherwise only limits silence.
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": {"temperature": 0, "num_ctx": self._num_ctx, "num_predict": self._num_predict},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt, "images": [base64.b64encode(image).decode("ascii")]},
            ],
        }
        deadline = time.monotonic() + self._request_timeout
        try:
            response = requests.post(f"{host}/api/chat", json=payload, timeout=self._timeout, stream=True)
        except requests.RequestException as exc:
            raise WorkerUnavailableException(str(exc)) from exc

        # Leaving this block for any reason closes the socket, which is what tells
        # the PC to stop working on the image.
        with response:
            if response.status_code >= 400:
                body = response.text[:300]
                # "repeat limit" is the model looping on this image, not the PC failing.
                if "repeat limit" in body:
                    raise WorkerOutputException("el modelo entró en un ciclo repetitivo")
                raise WorkerUnavailableException(f"HTTP {response.status_code}: {body}")
            content, done_reason = self._read_stream(response, deadline, should_stop)

        if not content.strip():
            reason = "se agotó el límite de respuesta" if done_reason == "length" else "respuesta vacía"
            raise WorkerOutputException(reason)

        data = parse_json_answer(content)
        return data if instructions else self._normalize(data)

    def _read_stream(
        self,
        response: requests.Response,
        deadline: float,
        should_stop: Optional[Callable[[], bool]],
    ) -> Tuple[str, Optional[str]]:
        """Joins the answer as it is written, one fragment per line of NDJSON.

        The stop and the clock are only looked at between fragments, which arrive
        several times a second while the model writes. A PC that goes quiet
        instead is cut by the socket's own read timeout."""
        parts: List[str] = []
        done_reason: Optional[str] = None
        try:
            for line in response.iter_lines(decode_unicode=True):
                if should_stop is not None and should_stop():
                    raise JobStoppedException()
                if time.monotonic() >= deadline:
                    raise WorkerTimeoutException(
                        f"el equipo no terminó en {self._request_timeout:.0f} segundos"
                    )
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                error = event.get("error")
                if error:
                    if "repeat limit" in str(error):
                        raise WorkerOutputException("el modelo entró en un ciclo repetitivo")
                    raise WorkerUnavailableException(str(error))
                parts.append((event.get("message") or {}).get("content") or "")
                if event.get("done"):
                    done_reason = event.get("done_reason")
                    break
        except requests.RequestException as exc:
            raise WorkerUnavailableException(str(exc)) from exc
        return "".join(parts), done_reason

    @staticmethod
    def _normalize(data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict) or not isinstance(data.get("full_text"), str):
            raise WorkerOutputException("falta el texto transcrito")
        fields = [
            {"name": str(f.get("name", "")).strip(), "value": str(f.get("value", "")).strip()}
            for f in data.get("fields") or []
            if isinstance(f, dict) and str(f.get("name", "")).strip()
        ]
        tables = [
            [[str(cell) for cell in row] for row in table if isinstance(row, list)]
            for table in data.get("tables") or []
            if isinstance(table, list)
        ]
        return {
            "document_type": str(data.get("document_type") or "").strip(),
            "full_text": data["full_text"],
            "fields": fields,
            "tables": tables,
        }
