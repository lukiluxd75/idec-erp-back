from typing import Optional

from app.domains.alignment.domain.entities.alignment_block import AlignmentBlock
from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)


class ConfirmAlignmentBlockUseCase:
    def __init__(self, repository: AlignmentBlockRepositoryPort):
        self._repository = repository

    def execute(self, block_id: int, confirmed_by_sub: Optional[str] = None) -> AlignmentBlock:
        return self._repository.confirm(block_id, confirmed_by_sub=confirmed_by_sub)
