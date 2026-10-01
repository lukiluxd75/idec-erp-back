import logging
import time
from typing import List, Optional

import requests

from app.core.config.settings import settings
from app.domains.folios.domain.entities.ocr_block import OcrBlock
from app.domains.folios.domain.exceptions import OcrUnavailableException
from app.domains.folios.domain.ports.ocr_port import OcrPort

logger = logging.getLogger("uvicorn.error")


class _TransientOcrFailure(OcrUnavailableException):
    """The service dropped the connection, timed out on a request, answered 5xx or
    marked the job as failed: things that often pass by themselves, so the page is
    sent again. Whatever is NOT this (not configured, a 4xx, an unreadable answer,
    the job still unfinished at the deadline) fails at once."""


class GamcOcrClient(OcrPort):
    """Server-side client of the GAMC OCR service -- same job API the browser
    uses in resolutions.api.js / geoextraction.api.js (POST /ocr/ -> job_id, poll
    GET /ocr/result/{job_id}/json until done/failed). Each result block is
    {points: 4 corners, text, confidence}; corners are reduced to their bounds."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: Optional[float] = None,
        retries: Optional[int] = None,
        retry_delay_seconds: Optional[float] = None,
        sleep=time.sleep,
    ):
        self._base = (base_url if base_url is not None else settings.FOLIOS_OCR_API_URL).rstrip("/")
        self._timeout = timeout_seconds or settings.FOLIOS_OCR_TIMEOUT_SECONDS
        self._poll = poll_interval_seconds or settings.FOLIOS_OCR_POLL_INTERVAL_SECONDS
        self._retries = settings.FOLIOS_OCR_RETRIES if retries is None else retries
        self._retry_delay = (
            settings.FOLIOS_OCR_RETRY_DELAY_SECONDS if retry_delay_seconds is None else retry_delay_seconds
        )
        self._sleep = sleep

    def read(self, image_bytes: bytes, filename: str = "pagina.jpg") -> List[OcrBlock]:
        """The blocks of one page. A transient failure resends the page (waiting
        longer each time) instead of losing the reading of a whole document over one
        hiccup of the service; the last failure is the one reported."""
        attempts = max(0, self._retries) + 1
        for attempt in range(1, attempts + 1):
            try:
                return self._read_once(image_bytes, filename)
            except _TransientOcrFailure as exc:
                if attempt == attempts:
                    raise OcrUnavailableException(
                        f"{exc.message} (tras {attempts} intento{'s' if attempts > 1 else ''})"
                    ) from exc
                delay = self._retry_delay * attempt
                logger.warning(
                    "OCR: %s -- reintento %d de %d en %.0f s (%s)",
                    exc.message, attempt, attempts - 1, delay, filename,
                )
                self._sleep(delay)
        raise OcrUnavailableException("El servicio OCR no respondió.")  # unreachable

    def _read_once(self, image_bytes: bytes, filename: str) -> List[OcrBlock]:
        if not self._base:
            raise OcrUnavailableException("El servicio OCR no está configurado (FOLIOS_OCR_API_URL).")
        deadline = time.monotonic() + self._timeout
        try:
            response = requests.post(
                f"{self._base}/ocr/",
                files={"file": (filename, image_bytes, "image/jpeg")},
                timeout=(10, min(60, self._timeout)),
            )
            self._check(response)
            job_id = response.json().get("job_id")
            if not job_id:
                raise OcrUnavailableException("El servicio OCR no devolvió un identificador de trabajo.")

            while time.monotonic() < deadline:
                response = requests.get(f"{self._base}/ocr/result/{job_id}/json", timeout=30)
                self._check(response)
                data = response.json()
                status = data.get("status")
                if status == "done":
                    return self._to_blocks((data.get("result") or {}).get("result") or [])
                if status == "failed":
                    raise _TransientOcrFailure("El servicio OCR marcó el trabajo como fallido.")
                time.sleep(self._poll)
        except requests.Timeout as exc:
            raise _TransientOcrFailure("El servicio OCR no respondió a tiempo.") from exc
        except requests.ConnectionError as exc:
            raise _TransientOcrFailure(
                f"No se pudo conectar con el servicio OCR ({exc.__class__.__name__})."
            ) from exc
        except requests.RequestException as exc:
            raise OcrUnavailableException(
                f"No se pudo conectar con el servicio OCR ({exc.__class__.__name__})."
            ) from exc
        except ValueError as exc:  # invalid JSON
            raise OcrUnavailableException("El servicio OCR devolvió una respuesta ilegible.") from exc
        raise OcrUnavailableException("Tiempo agotado esperando el resultado del OCR.")

    @staticmethod
    def _check(response) -> None:
        """A 5xx is the service having a bad moment (retry); a 4xx is the request
        being wrong (retrying would not change it)."""
        if 500 <= response.status_code < 600:
            raise _TransientOcrFailure(f"El servicio OCR respondió con error {response.status_code}.")
        response.raise_for_status()

    @staticmethod
    def _to_blocks(raw: list) -> List[OcrBlock]:
        blocks = []
        for item in raw:
            points = item.get("points") or []
            text = (item.get("text") or "").strip()
            if len(points) < 2 or not text:
                continue
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]
            blocks.append(OcrBlock(text, float(item.get("confidence") or 0.0), min(xs), min(ys), max(xs), max(ys)))
        return blocks
