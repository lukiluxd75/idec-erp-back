from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domains.digitization.domain.entities import DigitizationJob


class JobRepositoryPort(ABC):
    @abstractmethod
    def create(
        self,
        file_name: str,
        mime_type: str,
        image: bytes,
        prepared_image: bytes,
        requested_by: str,
        instructions: Optional[str] = None,
        output_template: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> DigitizationJob: ...

    @abstractmethod
    def get(self, job_id: str) -> Optional[DigitizationJob]: ...

    @abstractmethod
    def get_many(self, job_ids: List[str]) -> List[DigitizationJob]: ...

    @abstractmethod
    def get_prepared_image(self, job_id: str) -> Optional[bytes]: ...

    @abstractmethod
    def list_by_requester(self, requested_by: str, limit: int) -> List[DigitizationJob]: ...

    @abstractmethod
    def list_processing(self) -> List[DigitizationJob]: ...

    @abstractmethod
    def has_pending(self) -> bool: ...

    @abstractmethod
    def claim_next(self, worker_host: str) -> Optional[DigitizationJob]:
        """Atomically move the oldest pending job to processing on `worker_host`
        and count one attempt. None if the queue is empty."""

    @abstractmethod
    def mark_done(self, job_id: str, result: Dict[str, Any]) -> None: ...

    @abstractmethod
    def release(self, job_id: str, error: str) -> None:
        """Back to pending so another PC can take it."""

    @abstractmethod
    def mark_failed(self, job_id: str, error: str) -> None: ...

    @abstractmethod
    def requeue_orphaned(self, except_hosts: List[str]) -> int:
        """Processing jobs left behind by a dispatcher that died go back to pending,
        except those still running on `except_hosts`."""

    @abstractmethod
    def requeue_failed(self, job_id: str) -> Optional[DigitizationJob]:
        """Failed job back to pending with its attempts reset."""
