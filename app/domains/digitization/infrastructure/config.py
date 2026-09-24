from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class DigitizationSettings(BaseSettings):
    """Read from DIGITIZATION_* variables in .env. Kept inside the domain so the
    domain can be added or removed without touching core settings."""

    model_config = SettingsConfigDict(
        env_prefix="DIGITIZATION_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Comma-separated Ollama base URLs of the architects' PCs, e.g.
    # "http://172.16.0.11:11434,http://172.16.0.12:11434"
    worker_urls: str = ""
    # Every backend connected to the same database competes to dispatch the queue.
    # Set false on local development copies so only the deployed server sends
    # jobs to the PCs (a copy running older code would process them wrongly).
    dispatcher_enabled: bool = True
    vision_model: str = "qwen3-vl:4b"
    # Short keep-alive frees the PC's VRAM soon after a job, since the architect needs it back.
    keep_alive: str = "2m"
    # The installed qwen3-vl reasons before answering: the context must fit the
    # image, the reasoning and the JSON, or the answer comes back empty.
    num_ctx: int = 20480
    num_predict: int = 16000
    connect_timeout_seconds: float = 5.0
    request_timeout_seconds: float = 420.0
    health_timeout_seconds: float = 3.0
    poll_interval_seconds: float = 3.0
    host_cooldown_seconds: float = 60.0
    max_attempts: int = 3
    max_upload_mb: int = 20
    max_image_side: int = 2000

    @property
    def worker_hosts(self) -> List[str]:
        return [url.strip().rstrip("/") for url in self.worker_urls.split(",") if url.strip()]


@lru_cache()
def get_digitization_settings() -> DigitizationSettings:
    return DigitizationSettings()
