from typing import List

from app.domains.alignment.domain.entities.alignment_block import AlignmentBlock
from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)


class ListAlignmentBlocksUseCase:
    def __init__(self, repository: AlignmentBlockRepositoryPort):
        self._repository = repository

    def execute(self, year: int) -> List[AlignmentBlock]:
        return self._repository.list_by_year(year)
