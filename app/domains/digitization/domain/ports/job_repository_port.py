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
    def find_processing_on(self, worker_host: str) -> Optional[DigitizationJob]:
        """The job that PC is running right now, if any."""

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
    def request_stop(self, job_id: str) -> None:
        """Raise the flag that asks whoever is running this job to drop it. The
        run may be in another backend process, so the database is the only channel."""

    @abstractmethod
    def stop_requested(self, job_id: str) -> bool: ...

    @abstractmethod
    def mark_stopped(self, job_id: str, error: str) -> None:
        """The run was abandoned on request. Retryable by hand, never on its own."""

    @abstractmethod
    def requeue_orphaned(self, except_hosts: List[str]) -> int:
        """Processing jobs left behind by a dispatcher that died go back to pending,
        except those still running on `except_hosts`."""

    @abstractmethod
    def requeue_failed(self, job_id: str) -> Optional[DigitizationJob]:
        """Failed or stopped job back to pending with its attempts reset."""
