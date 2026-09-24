from app.domains.digitization.domain.entities import DigitizationJob, JobStatus
from app.domains.digitization.domain.exceptions import JobNotFoundException, JobNotRetryableException
from app.domains.digitization.domain.ports import JobRepositoryPort


class RetryJobUseCase:
    def __init__(self, repository: JobRepositoryPort):
        self._repository = repository

    def execute(self, job_id: str, requested_by: str) -> DigitizationJob:
        job = self._repository.get(job_id)
        if job is None or job.requested_by != requested_by:
            raise JobNotFoundException()
        # A job someone stopped is a dead end like a failed one, and just as
        # sendable again: stopping it was a decision, not a verdict on the image.
        if job.status not in (JobStatus.FAILED, JobStatus.STOPPED):
            raise JobNotRetryableException()
        requeued = self._repository.requeue_failed(job_id)
        if requeued is None:
            raise JobNotRetryableException()
        return requeued
