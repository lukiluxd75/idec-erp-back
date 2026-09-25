from concurrent.futures import ThreadPoolExecutor
from typing import List

from app.domains.digitization.domain.entities import WorkerStatus
from app.domains.digitization.domain.ports import HostUsagePort, JobRepositoryPort, VisionWorkerPort

DIGITIZATION = "digitization"


class CheckWorkersUseCase:
    def __init__(
        self,
        repository: JobRepositoryPort,
        worker: VisionWorkerPort,
        hosts: List[str],
        usage: HostUsagePort,
    ):
        self._repository = repository
        self._worker = worker
        self._hosts = hosts
        self._usage = usage

    def execute(self) -> List[WorkerStatus]:
        if not self._hosts:
            return []
        with ThreadPoolExecutor(max_workers=len(self._hosts)) as pool:
            statuses = list(pool.map(self._worker.check, self._hosts))
        running = {job.worker_host: job.id for job in self._repository.list_processing()}
        borrowed = self._usage.active()
        for status in statuses:
            status.current_job_id = running.get(status.host)
            # A digitization job wins the label: it is the only usage with an id to show.
            status.used_by = DIGITIZATION if status.current_job_id else borrowed.get(status.host)
        return statuses
