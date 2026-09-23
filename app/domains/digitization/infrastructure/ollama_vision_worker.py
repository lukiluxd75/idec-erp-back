import base64
import json
from typing import Any, Dict

import requests

from app.domains.digitization.domain.entities import WorkerStatus
from app.domains.digitization.domain.exceptions import WorkerOutputException, WorkerUnavailableException
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

RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "document_type": {"type": "string"},
        "full_text": {"type": "string"},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                "required": ["name", "value"],
            },
        },
        "tables": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
        },
    },
    "required": ["document_type", "full_text", "fields", "tables"],
}


class OllamaVisionWorker(VisionWorkerPort):
    def __init__(
        self,
        model: str,
        keep_alive: str,
        connect_timeout: float,
        request_timeout: float,
        health_timeout: float,
    ):
        self._model = model
        self._keep_alive = keep_alive
        self._timeout = (connect_timeout, request_timeout)
        self._health_timeout = health_timeout

    def check(self, host: str) -> WorkerStatus:
        try:
            response = requests.get(f"{host}/api/tags", timeout=self._health_timeout)
            response.raise_for_status()
            models = response.json().get("models", [])
        except (requests.RequestException, ValueError, AttributeError):
            return WorkerStatus(host=host, reachable=False, model_available=False)
        names = {m.get("name") for m in models if isinstance(m, dict)} | {
            m.get("model") for m in models if isinstance(m, dict)
        }
        wanted = {self._model, f"{self._model}:latest"}
        return WorkerStatus(host=host, reachable=True, model_available=bool(names & wanted))

    def extract(self, host: str, image: bytes) -> Dict[str, Any]:
        payload = {
            "model": self._model,
            "stream": False,
            "format": RESULT_SCHEMA,
            "keep_alive": self._keep_alive,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT, "images": [base64.b64encode(image).decode("ascii")]},
            ],
        }
        try:
            response = requests.post(f"{host}/api/chat", json=payload, timeout=self._timeout)
        except requests.RequestException as exc:
            raise WorkerUnavailableException(str(exc)) from exc
        if response.status_code >= 400:
            raise WorkerUnavailableException(f"HTTP {response.status_code}: {response.text[:300]}")

        try:
            content = response.json()["message"]["content"]
            data = json.loads(content)
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkerOutputException(f"respuesta no es JSON válido ({exc})") from exc
        return self._normalize(data)

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
