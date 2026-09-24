from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.domains.digitization.domain.entities import WorkerStatus


class VisionWorkerPort(ABC):
    """One of the architects' PCs running the vision model."""

    @abstractmethod
    def check(self, host: str) -> WorkerStatus:
        """Quick health check. Never raises."""

    @abstractmethod
    def extract(
        self,
        host: str,
        image: bytes,
        instructions: Optional[str] = None,
        output_template: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Structured digitization of one image: generic when `instructions` is
        None, otherwise shaped like `output_template`. Raises
        WorkerUnavailableException or WorkerOutputException."""
