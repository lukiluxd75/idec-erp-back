from typing import List

from app.domains.digitization.domain.entities import DigitizationJob
from app.domains.digitization.domain.ports import JobRepositoryPort


class ListJobsUseCase:
    def __init__(self, repository: JobRepositoryPort):
        self._repository = repository

    def execute(self, requested_by: str, limit: int = 50) -> List[DigitizationJob]:
        return self._repository.list_by_requester(requested_by, max(1, min(limit, 200)))
