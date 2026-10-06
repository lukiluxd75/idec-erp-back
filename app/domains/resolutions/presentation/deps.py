from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import SessionLocal, get_db
from app.domains.resolutions.application.use_cases import (
    AddPlanPagesUseCase,
    CreateResolutionUseCase,
    DeletePlanPageUseCase,
    DeleteResolutionUseCase,
    DetectPlanPagePlantaUseCase,
    RequestPlantaDetectionUseCase,
    SetPlanPagePlantasUseCase,
    SaveTableUseCase,
    GetPlanPageUseCase,
    ListResolutionsUseCase,
    GetPageUseCase,
    GetResolutionUseCase,
)
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort
from app.domains.resolutions.infrastructure.gamc_ocr_client import GamcPlanOcrClient
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


def get_add_plan_pages_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> AddPlanPagesUseCase:
    return AddPlanPagesUseCase(repository=repo)


def get_get_plan_page_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> GetPlanPageUseCase:
    return GetPlanPageUseCase(repository=repo)


def get_delete_plan_page_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> DeletePlanPageUseCase:
    return DeletePlanPageUseCase(repository=repo)


def get_set_plan_page_plantas_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> SetPlanPagePlantasUseCase:
    return SetPlanPagePlantasUseCase(repository=repo)


def get_request_planta_detection_use_case(
    repo: ResolutionRepositoryPort = Depends(get_resolution_repository),
) -> RequestPlantaDetectionUseCase:
    return RequestPlantaDetectionUseCase(repository=repo)


def run_detect_plan_page_planta(resolution_id: str, order_index: int) -> None:
    """Entry point for the background planta detection. Runs after the
    upload request has returned, so it cannot use the request's DB session
    (already closed) -- it opens and closes its own."""
    db = SessionLocal()
    try:
        DetectPlanPagePlantaUseCase(
            repository=SqlResolutionRepository(db=db),
            ocr=GamcPlanOcrClient(),
        ).execute(resolution_id, order_index)
    finally:
        db.close()


@lru_cache()
def get_connection_manager() -> ResolutionsConnectionManager:
    """Cached singleton: all requests/sockets in the same uvicorn process
    must share the same connection registry."""
    return ResolutionsConnectionManager()
