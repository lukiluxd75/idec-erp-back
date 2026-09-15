from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.resolutions.application.use_cases import (
    CreateResolutionUseCase,
    DeleteResolutionUseCase,
    SaveTableUseCase,
    ListResolutionsUseCase,
    GetPageUseCase,
    GetResolutionUseCase,
)
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort
from app.domains.resolutions.infrastructure.sql_resolution_repository import SqlResolutionRepository
from app.domains.resolutions.infrastructure.ws_connection_manager import ResolutionsConnectionManager


def get_resolution_repository(db: Session = Depends(get_db)) -> ResolutionRepositoryPort:
    return SqlResolutionRepository(db=db)


def get_list_resolutions_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> ListResolutionsUseCase:
    return ListResolutionsUseCase(repository=repo)


def get_resolution_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> GetResolutionUseCase:
    return GetResolutionUseCase(repository=repo)


def get_page_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> GetPageUseCase:
    return GetPageUseCase(repository=repo)


def get_save_table_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> SaveTableUseCase:
    return SaveTableUseCase(repository=repo)


def get_delete_resolution_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> DeleteResolutionUseCase:
    return DeleteResolutionUseCase(repository=repo)


def get_create_resolution_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> CreateResolutionUseCase:
    return CreateResolutionUseCase(repository=repo)


@lru_cache()
def get_connection_manager() -> ResolutionsConnectionManager:
    """Cached singleton: all requests/sockets in the same uvicorn process
    must share the same connection registry."""
    return ResolutionsConnectionManager()
