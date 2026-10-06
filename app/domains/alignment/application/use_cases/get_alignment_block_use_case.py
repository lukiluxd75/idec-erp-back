from typing import Optional

from app.domains.alignment.domain.entities.alignment_block import AlignmentBlockDetail
from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)


class GetAlignmentBlockUseCase:
    def __init__(self, repository: AlignmentBlockRepositoryPort):
        self._repository = repository

    def execute(self, block_id: int) -> Optional[AlignmentBlockDetail]:
        return self._repository.get(block_id)
