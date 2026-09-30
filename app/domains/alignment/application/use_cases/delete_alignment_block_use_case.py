from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)


class DeleteAlignmentBlockUseCase:
    def __init__(self, repository: AlignmentBlockRepositoryPort):
        self._repository = repository

    def execute(self, block_id: int) -> None:
        self._repository.delete(block_id)
