from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Set

from app.domains.digitization.domain.entities import WorkerStatus


class VisionWorkerPort(ABC):
    """One of the architects' PCs running the vision model."""

    @abstractmethod
    def check(self, host: str) -> WorkerStatus:
        """Quick health check. Never raises."""

    @abstractmethod
    def models(self, host: str) -> Optional[Set[str]]:
        """Model names installed on that PC, or None if it does not respond.
        Never raises."""

    @abstractmethod
    def extract(
        self,
        host: str,
        image: bytes,
        instructions: Optional[str] = None,
        output_template: Optional[Dict[str, Any]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Structured digitization of one image: generic when `instructions` is
        None, otherwise shaped like `output_template`.

        `should_stop` is asked repeatedly while the answer is being written; the
        moment it returns True the run is abandoned and JobStoppedException is
        raised. Also raises WorkerUnavailableException, WorkerOutputException or
        WorkerTimeoutException."""
