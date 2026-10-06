from dataclasses import dataclass
from typing import List, Optional

from app.domains.digitization.domain.exceptions import NoJobRunningException, WorkerNotFoundException
from app.domains.digitization.domain.ports import HostUsagePort, JobRepositoryPort

DIGITIZATION = "digitization"


@dataclass(frozen=True)
class StoppedWork:
    host: str
    used_by: str
    job_id: Optional[str] = None


class StopWorkerUseCase:
    """Lets an operator cut short whatever a PC is stuck on, whoever started it:
    a document from the digitization queue, or a call another domain borrowed the
    PC for.

    Either way it only raises a flag, because the work itself is running in
    whichever backend process took it. That process reads the flag within a
    couple of seconds and hangs up on the PC, so the work is not stopped when
    this returns, it is stopped shortly after."""

    def __init__(self, repository: JobRepositoryPort, usage: HostUsagePort, hosts: List[str]):
        self._repository = repository
        self._usage = usage
        self._hosts = hosts

    def execute(self, host: str) -> StoppedWork:
        normalized = str(host or "").strip().rstrip("/")
        if normalized not in self._hosts:
            raise WorkerNotFoundException()

        job = self._repository.find_processing_on(normalized)
        if job is not None:
            self._repository.request_stop(job.id)
            return StoppedWork(host=normalized, used_by=DIGITIZATION, job_id=job.id)

        borrowed_by = self._usage.active().get(normalized)
        if borrowed_by is None or self._usage.request_stop(normalized) == 0:
            raise NoJobRunningException()
        return StoppedWork(host=normalized, used_by=borrowed_by)
