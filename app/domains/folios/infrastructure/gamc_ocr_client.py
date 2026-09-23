import time
from typing import List, Optional

import requests

from app.core.config.settings import settings
from app.domains.folios.domain.entities.ocr_block import OcrBlock
from app.domains.folios.domain.exceptions import OcrUnavailableException
from app.domains.folios.domain.ports.ocr_port import OcrPort


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
    ):
        self._base = (base_url if base_url is not None else settings.FOLIOS_OCR_API_URL).rstrip("/")
        self._timeout = timeout_seconds or settings.FOLIOS_OCR_TIMEOUT_SECONDS
        self._poll = poll_interval_seconds or settings.FOLIOS_OCR_POLL_INTERVAL_SECONDS

    def read(self, image_bytes: bytes, filename: str = "pagina.jpg") -> List[OcrBlock]:
        if not self._base:
            raise OcrUnavailableException("El servicio OCR no está configurado (FOLIOS_OCR_API_URL).")
        deadline = time.monotonic() + self._timeout
        try:
            response = requests.post(
                f"{self._base}/ocr/",
                files={"file": (filename, image_bytes, "image/jpeg")},
                timeout=min(60, self._timeout),
            )
            response.raise_for_status()
            job_id = response.json().get("job_id")
            if not job_id:
                raise OcrUnavailableException("El servicio OCR no devolvió un identificador de trabajo.")

            while time.monotonic() < deadline:
                response = requests.get(f"{self._base}/ocr/result/{job_id}/json", timeout=30)
                response.raise_for_status()
                data = response.json()
                status = data.get("status")
                if status == "done":
                    return self._to_blocks((data.get("result") or {}).get("result") or [])
                if status == "failed":
                    raise OcrUnavailableException("El servicio OCR marcó el trabajo como fallido.")
                time.sleep(self._poll)
        except requests.Timeout as exc:
            raise OcrUnavailableException("El servicio OCR no respondió a tiempo.") from exc
        except requests.RequestException as exc:
            raise OcrUnavailableException(f"No se pudo conectar con el servicio OCR ({exc.__class__.__name__}).") from exc
        except ValueError as exc:  # invalid JSON
            raise OcrUnavailableException("El servicio OCR devolvió una respuesta ilegible.") from exc
        raise OcrUnavailableException("Tiempo agotado esperando el resultado del OCR.")

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
