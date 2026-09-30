from app.domains.alignment.domain.entities.alignment_block import AlignmentCoverage
from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)


class GetAlignmentCoverageUseCase:
    def __init__(self, repository: AlignmentBlockRepositoryPort):
        self._repository = repository

    def execute(self, year: int) -> AlignmentCoverage:
        return self._repository.coverage(year)
