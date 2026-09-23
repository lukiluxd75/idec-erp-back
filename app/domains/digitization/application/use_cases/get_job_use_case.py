from app.domains.digitization.domain.entities import DigitizationJob
from app.domains.digitization.domain.exceptions import JobNotFoundException
from app.domains.digitization.domain.ports import JobRepositoryPort


class GetJobUseCase:
    def __init__(self, repository: JobRepositoryPort):
        self._repository = repository

    def execute(self, job_id: str, requested_by: str) -> DigitizationJob:
        job = self._repository.get(job_id)
        # Someone else's job is reported as missing, not forbidden, to avoid leaking ids.
        if job is None or job.requested_by != requested_by:
            raise JobNotFoundException()
        return job
