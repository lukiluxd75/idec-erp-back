from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.core.database.connection import SessionLocal, get_db
from app.domains.folios.application.use_cases import (
    DeleteFolioUseCase,
    GetFolioDiagnosticsUseCase,
    GetFolioFillLogUseCase,
    GetFolioPageImageUseCase,
    GetFolioUseCase,
    ListFoliosUseCase,
    ProcessFolioUseCase,
    RequestReprocessUseCase,
    ReviewFolioUseCase,
    UploadFolioUseCase,
)
from app.domains.folios.domain.ports.asiento_structurer_port import AsientoStructurerPort
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort
from app.domains.folios.domain.ports.ocr_port import OcrPort
from app.domains.folios.domain.ports.page_image_port import PageImagePort
from app.domains.folios.infrastructure.gamc_ocr_client import GamcOcrClient
from app.domains.folios.infrastructure.ollama_asiento_structurer import OllamaAsientoStructurer
from app.domains.folios.infrastructure.opencv_page_image import OpenCvPageImage
from app.domains.folios.infrastructure.sql_folio_repository import SqlFolioRepository
from app.domains.folios.infrastructure.ws_connection_manager import FoliosConnectionManager


def get_folio_repository(db: Session = Depends(get_db)) -> FolioRepositoryPort:
    return SqlFolioRepository(db=db)


@lru_cache()
def get_ocr() -> OcrPort:
    return GamcOcrClient()


@lru_cache()
def get_page_images() -> PageImagePort:
    return OpenCvPageImage()


@lru_cache()
def get_asiento_structurer() -> AsientoStructurerPort:
    return OllamaAsientoStructurer()


@lru_cache()
def get_connection_manager() -> FoliosConnectionManager:
    """Singleton per process: every request/socket of a worker shares it."""
    return FoliosConnectionManager()


def run_process_folio(folio_id: str) -> None:
    """Entry point for the background pipeline. Runs after the upload request
    has returned, so it cannot use the request's DB session (already closed) --
    it opens and closes its own."""
    db = SessionLocal()
    try:
        ProcessFolioUseCase(
            repository=SqlFolioRepository(db=db),
            ocr=get_ocr(),
            images=get_page_images(),
            structurer=get_asiento_structurer(),
            confidence_threshold=settings.FOLIOS_CONFIDENCE_THRESHOLD,
        ).execute(folio_id)
    finally:
        db.close()


def get_upload_folio_use_case(repo: FolioRepositoryPort = Depends(get_folio_repository)) -> UploadFolioUseCase:
    return UploadFolioUseCase(repository=repo)


def get_list_folios_use_case(repo: FolioRepositoryPort = Depends(get_folio_repository)) -> ListFoliosUseCase:
    return ListFoliosUseCase(repository=repo)


def get_folio_use_case(repo: FolioRepositoryPort = Depends(get_folio_repository)) -> GetFolioUseCase:
    return GetFolioUseCase(repository=repo)


def get_folio_page_image_use_case(
    repo: FolioRepositoryPort = Depends(get_folio_repository),
) -> GetFolioPageImageUseCase:
    return GetFolioPageImageUseCase(repository=repo)


def get_folio_diagnostics_use_case(
    repo: FolioRepositoryPort = Depends(get_folio_repository),
) -> GetFolioDiagnosticsUseCase:
    return GetFolioDiagnosticsUseCase(repository=repo)


def get_folio_fill_log_use_case(
    repo: FolioRepositoryPort = Depends(get_folio_repository),
) -> GetFolioFillLogUseCase:
    return GetFolioFillLogUseCase(repository=repo)


def get_review_folio_use_case(repo: FolioRepositoryPort = Depends(get_folio_repository)) -> ReviewFolioUseCase:
    return ReviewFolioUseCase(repository=repo)


def get_request_reprocess_use_case(
    repo: FolioRepositoryPort = Depends(get_folio_repository),
) -> RequestReprocessUseCase:
    return RequestReprocessUseCase(repository=repo)


def get_delete_folio_use_case(repo: FolioRepositoryPort = Depends(get_folio_repository)) -> DeleteFolioUseCase:
    return DeleteFolioUseCase(repository=repo)
