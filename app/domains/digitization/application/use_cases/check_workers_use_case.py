from concurrent.futures import ThreadPoolExecutor
from typing import List

from app.domains.digitization.domain.entities import WorkerStatus
from app.domains.digitization.domain.ports import JobRepositoryPort, VisionWorkerPort


class CheckWorkersUseCase:
    def __init__(self, repository: JobRepositoryPort, worker: VisionWorkerPort, hosts: List[str]):
        self._repository = repository
        self._worker = worker
        self._hosts = hosts

    def execute(self) -> List[WorkerStatus]:
        if not self._hosts:
            return []
        with ThreadPoolExecutor(max_workers=len(self._hosts)) as pool:
            statuses = list(pool.map(self._worker.check, self._hosts))
        running = {job.worker_host: job.id for job in self._repository.list_processing()}
        for status in statuses:
            status.current_job_id = running.get(status.host)
        return statuses
