from typing import List

from app.domains.digitization.domain.entities import DigitizationJob
from app.domains.digitization.domain.ports import JobRepositoryPort


class GetJobsUseCase:
    """Status of several jobs at once, for domains that enqueued them."""

    def __init__(self, repository: JobRepositoryPort):
        self._repository = repository

    def execute(self, job_ids: List[str]) -> List[DigitizationJob]:
        return self._repository.get_many(list(dict.fromkeys(job_ids)))
