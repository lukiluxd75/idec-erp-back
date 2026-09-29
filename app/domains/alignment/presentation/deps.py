from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.alignment.application.use_cases import (
    ConfirmAlignmentBlockUseCase,
    CreateAlignmentBlockUseCase,
    DeleteAlignmentBlockUseCase,
    GetAlignmentBlockUseCase,
    GetAlignmentCoverageUseCase,
    ListAlignmentBlocksUseCase,
    UpdateAlignmentBlockUseCase,
)
from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)
from app.domains.alignment.infrastructure.sql_alignment_block_repository import (
    SqlAlignmentBlockRepository,
)


def get_alignment_block_repository(db: Session = Depends(get_db)) -> AlignmentBlockRepositoryPort:
    return SqlAlignmentBlockRepository(db=db)


def get_create_alignment_block_use_case(
    repository: AlignmentBlockRepositoryPort = Depends(get_alignment_block_repository),
) -> CreateAlignmentBlockUseCase:
    return CreateAlignmentBlockUseCase(repository=repository)


def get_list_alignment_blocks_use_case(
    repository: AlignmentBlockRepositoryPort = Depends(get_alignment_block_repository),
) -> ListAlignmentBlocksUseCase:
    return ListAlignmentBlocksUseCase(repository=repository)


def get_get_alignment_block_use_case(
    repository: AlignmentBlockRepositoryPort = Depends(get_alignment_block_repository),
) -> GetAlignmentBlockUseCase:
    return GetAlignmentBlockUseCase(repository=repository)


def get_update_alignment_block_use_case(
    repository: AlignmentBlockRepositoryPort = Depends(get_alignment_block_repository),
) -> UpdateAlignmentBlockUseCase:
    return UpdateAlignmentBlockUseCase(repository=repository)


def get_confirm_alignment_block_use_case(
    repository: AlignmentBlockRepositoryPort = Depends(get_alignment_block_repository),
) -> ConfirmAlignmentBlockUseCase:
    return ConfirmAlignmentBlockUseCase(repository=repository)


def get_delete_alignment_block_use_case(
    repository: AlignmentBlockRepositoryPort = Depends(get_alignment_block_repository),
) -> DeleteAlignmentBlockUseCase:
    return DeleteAlignmentBlockUseCase(repository=repository)


def get_get_alignment_coverage_use_case(
    repository: AlignmentBlockRepositoryPort = Depends(get_alignment_block_repository),
) -> GetAlignmentCoverageUseCase:
    return GetAlignmentCoverageUseCase(repository=repository)
