import time
from typing import List

import requests
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config.settings import settings
from app.domains.resolutions.domain.exceptions import PlanOcrUnavailableException
from app.domains.resolutions.domain.plan_title import TitleBlock
from app.domains.resolutions.domain.ports.plan_ocr_port import PlanOcrPort


class ResolutionsOcrSettings(BaseSettings):
    """RESOLUTIONS_OCR_* del .env. Vacío = el mismo servicio OCR del GAMC que
    ya usa folios (FOLIOS_OCR_API_URL), así no hace falta configurar nada nuevo
    en el servidor. Queda dentro del dominio para no tocar core/settings."""

    model_config = SettingsConfigDict(
        env_prefix="RESOLUTIONS_OCR_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    api_url: str = ""
    timeout_seconds: float = 120.0
    poll_interval_seconds: float = 1.5


class GamcPlanOcrClient(PlanOcrPort):
    """Cliente del servicio OCR del GAMC desde el servidor -- la misma API de
    trabajos que usa el navegador en resolutions.api.js (POST /ocr/ -> job_id,
    GET /ocr/result/{job_id}/json hasta done/failed). Cada bloque del resultado
    es {points: 4 esquinas, text, confidence}; las esquinas se reducen a su
    rectángulo."""

    def __init__(self, config: ResolutionsOcrSettings = None):
        config = config or ResolutionsOcrSettings()
        self._base = (config.api_url or settings.FOLIOS_OCR_API_URL or "").rstrip("/")
        self._timeout = config.timeout_seconds
        self._poll = config.poll_interval_seconds

    def read(self, image_bytes: bytes, filename: str = "plano.jpg") -> List[TitleBlock]:
        if not self._base:
            raise PlanOcrUnavailableException(
                "El servicio OCR no está configurado (RESOLUTIONS_OCR_API_URL o FOLIOS_OCR_API_URL)."
            )
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
                raise PlanOcrUnavailableException("El servicio OCR no devolvió un identificador de trabajo.")

            while time.monotonic() < deadline:
                response = requests.get(f"{self._base}/ocr/result/{job_id}/json", timeout=30)
                response.raise_for_status()
                data = response.json()
                status = data.get("status")
                if status == "done":
                    return self._to_blocks((data.get("result") or {}).get("result") or [])
                if status == "failed":
                    raise PlanOcrUnavailableException("El servicio OCR marcó el trabajo como fallido.")
                time.sleep(self._poll)
        except requests.Timeout as exc:
            raise PlanOcrUnavailableException("El servicio OCR no respondió a tiempo.") from exc
        except requests.RequestException as exc:
            raise PlanOcrUnavailableException(
                f"No se pudo conectar con el servicio OCR ({exc.__class__.__name__})."
            ) from exc
        except ValueError as exc:  # JSON inválido
            raise PlanOcrUnavailableException("El servicio OCR devolvió una respuesta ilegible.") from exc
        raise PlanOcrUnavailableException("Tiempo agotado esperando el resultado del OCR.")

    @staticmethod
    def _to_blocks(raw: list) -> List[TitleBlock]:
        blocks = []
        for item in raw:
            points = item.get("points") or []
            text = (item.get("text") or "").strip()
            if len(points) < 2 or not text:
                continue
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]
            blocks.append(TitleBlock(text, min(xs), min(ys), max(xs), max(ys)))
        return blocks
