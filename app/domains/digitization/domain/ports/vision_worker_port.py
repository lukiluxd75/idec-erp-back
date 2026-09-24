from abc import ABC, abstractmethod
from typing import Any, Dict

from app.domains.digitization.domain.entities import WorkerStatus


class VisionWorkerPort(ABC):
    """One of the architects' PCs running the vision model."""

    @abstractmethod
    def check(self, host: str) -> WorkerStatus:
        """Quick health check. Never raises."""

    @abstractmethod
    def extract(self, host: str, image: bytes) -> Dict[str, Any]:
        """Structured digitization of one image. Raises WorkerUnavailableException
        or WorkerOutputException."""
