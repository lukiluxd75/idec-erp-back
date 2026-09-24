from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.folder_analysis.application.document_synchronizer import DocumentSynchronizer
from app.domains.folder_analysis.application.use_cases import (
    AnalyzeDocumentUseCase,
    CreateDocumentUseCase,
    DeleteCaptureUseCase,
    DeleteDocumentUseCase,
    GetCaptureImageUseCase,
    GetDocumentUseCase,
    ListDocumentsUseCase,
    ListInboxUseCase,
    ReviewDocumentUseCase,
    SetDocumentPagesUseCase,
    UploadCapturesUseCase,
)
from app.domains.folder_analysis.domain.ports import (
    CaptureRepositoryPort,
    DocumentRepositoryPort,
    ExtractionQueuePort,
    ThumbnailPort,
)
from app.domains.folder_analysis.infrastructure.digitization_queue import DigitizationQueue
from app.domains.folder_analysis.infrastructure.opencv_thumbnail import OpenCvThumbnail
from app.domains.folder_analysis.infrastructure.sql_capture_repository import SqlCaptureRepository
from app.domains.folder_analysis.infrastructure.sql_document_repository import SqlDocumentRepository


@lru_cache()
def get_thumbnails() -> ThumbnailPort:
    return OpenCvThumbnail()


def get_capture_repository(db: Session = Depends(get_db)) -> CaptureRepositoryPort:
    return SqlCaptureRepository(db)


def get_document_repository(db: Session = Depends(get_db)) -> DocumentRepositoryPort:
    return SqlDocumentRepository(db)


def get_queue(db: Session = Depends(get_db)) -> ExtractionQueuePort:
    return DigitizationQueue(db)


def get_synchronizer(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    queue: ExtractionQueuePort = Depends(get_queue),
) -> DocumentSynchronizer:
    return DocumentSynchronizer(documents, queue)


def get_upload_captures_use_case(
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> UploadCapturesUseCase:
    return UploadCapturesUseCase(captures, get_thumbnails())


def get_list_inbox_use_case(captures: CaptureRepositoryPort = Depends(get_capture_repository)) -> ListInboxUseCase:
    return ListInboxUseCase(captures)


def get_capture_image_use_case(
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> GetCaptureImageUseCase:
    return GetCaptureImageUseCase(captures)


def get_delete_capture_use_case(
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> DeleteCaptureUseCase:
    return DeleteCaptureUseCase(captures)


def get_create_document_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> CreateDocumentUseCase:
    return CreateDocumentUseCase(documents, captures)


def get_set_pages_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> SetDocumentPagesUseCase:
    return SetDocumentPagesUseCase(documents, captures)


def get_delete_document_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> DeleteDocumentUseCase:
    return DeleteDocumentUseCase(documents, captures)


def get_analyze_document_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
    queue: ExtractionQueuePort = Depends(get_queue),
) -> AnalyzeDocumentUseCase:
    return AnalyzeDocumentUseCase(documents, captures, queue)


def get_get_document_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    synchronizer: DocumentSynchronizer = Depends(get_synchronizer),
) -> GetDocumentUseCase:
    return GetDocumentUseCase(documents, synchronizer)


def get_list_documents_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    synchronizer: DocumentSynchronizer = Depends(get_synchronizer),
) -> ListDocumentsUseCase:
    return ListDocumentsUseCase(documents, synchronizer)


def get_review_document_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
) -> ReviewDocumentUseCase:
    return ReviewDocumentUseCase(documents)
