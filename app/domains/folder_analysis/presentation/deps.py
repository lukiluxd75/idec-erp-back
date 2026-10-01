from functools import lru_cache
from typing import Dict

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import SessionLocal, get_db
from app.domains.digitization.contracts import get_borrow_host, get_worker_host_picker
from app.domains.folder_analysis.application.document_synchronizer import DocumentSynchronizer
from app.domains.folder_analysis.application.use_cases import (
    AddDocumentsToRegisteredFolderUseCase,
    AnalyzeDocumentUseCase,
    CreateDocumentUseCase,
    CreateRegisteredFolderUseCase,
    ClearInboxUseCase,
    DeleteCaptureUseCase,
    DeleteDocumentUseCase,
    DeleteRegisteredFolderUseCase,
    GetCaptureImageUseCase,
    GetDocumentUseCase,
    GetRegisteredFolderUseCase,
    ListDocumentsUseCase,
    ListReviewedDocumentsUseCase,
    ListInboxUseCase,
    GenerateCadastralCroquisUseCase,
    ListRegisteredFoldersUseCase,
    LookupCadastralParcelUseCase,
    RegisteredFolderService,
    RemoveDocumentFromRegisteredFolderUseCase,
    ReviewDocumentUseCase,
    RunServerReadingUseCase,
    SetDocumentPagesUseCase,
    UpdateRegisteredFolderUseCase,
    UploadCapturesUseCase,
)
from app.domains.folder_analysis.domain.entities import DocumentType
from app.domains.folder_analysis.domain.ports import (
    CaptureRepositoryPort,
    DocumentRepositoryPort,
    CadastralGisPort,
    ExtractionQueuePort,
    FolioExtractionPort,
    PdfRasterizerPort,
    RegisteredFolderRepositoryPort,
    ServerReadingPort,
    TaxExtractionPort,
    TaxStructurerPort,
    ThumbnailPort,
)
from app.domains.folder_analysis.infrastructure.arcgis_cadastral_gis import ArcGisCadastralGis
from app.domains.folder_analysis.infrastructure.digitization_queue import DigitizationQueue
from app.domains.folder_analysis.infrastructure.folios_extractor import FoliosExtractor
from app.domains.folder_analysis.infrastructure.ocr_plan_extractor import OcrPlanExtractor
from app.domains.folder_analysis.infrastructure.ocr_tax_extractor import OcrTaxExtractor
from app.domains.folder_analysis.infrastructure.ollama_fur_structurer import OllamaFurStructurer
from app.domains.folder_analysis.infrastructure.opencv_thumbnail import OpenCvThumbnail
from app.domains.folder_analysis.infrastructure.pdfium_rasterizer import PdfiumRasterizer
from app.domains.folder_analysis.infrastructure.sql_capture_repository import SqlCaptureRepository
from app.domains.folder_analysis.infrastructure.sql_document_repository import SqlDocumentRepository
from app.domains.folder_analysis.infrastructure.sql_registered_folder_repository import (
    SqlRegisteredFolderRepository,
)


@lru_cache()
def get_thumbnails() -> ThumbnailPort:
    return OpenCvThumbnail()


@lru_cache()
def get_pdf_rasterizer() -> PdfRasterizerPort:
    return PdfiumRasterizer()


def get_capture_repository(db: Session = Depends(get_db)) -> CaptureRepositoryPort:
    return SqlCaptureRepository(db)


def get_document_repository(db: Session = Depends(get_db)) -> DocumentRepositoryPort:
    return SqlDocumentRepository(db)


def get_registered_folder_repository(
    db: Session = Depends(get_db),
) -> RegisteredFolderRepositoryPort:
    return SqlRegisteredFolderRepository(db)


def get_queue(db: Session = Depends(get_db)) -> ExtractionQueuePort:
    return DigitizationQueue(db)


@lru_cache()
def get_folio_extractor() -> FolioExtractionPort:
    return FoliosExtractor()


@lru_cache()
def get_tax_structurer() -> TaxStructurerPort:
    """Borrows the architects' PCs from digitization (its public contract), the
    same way the folios pipeline does, instead of pinning one Ollama host."""
    return OllamaFurStructurer(
        host_provider=get_worker_host_picker().execute,
        borrow=get_borrow_host("folder-analysis").execute,
    )


@lru_cache()
def get_tax_extractor() -> TaxExtractionPort:
    return OcrTaxExtractor(structurer=get_tax_structurer())


@lru_cache()
def get_plan_extractor() -> ServerReadingPort:
    return OcrPlanExtractor()


@lru_cache()
def get_server_readers() -> Dict[str, ServerReadingPort]:
    """Every lane is read here with PaddleOCR and OpenCV instead of on the
    architects' PCs.

    A folio and a comprobante have rules that know their layout. The rest -- the
    plano and the documents the carpeta de poseedores brought in -- have no rules
    yet, so they get the same generic reading the plano already used: the sheet's
    text, its labelled values and its tables, with the meaning left to the
    architect. When one of them gets its own reader, it replaces its entry here.
    """
    generic = get_plan_extractor()
    readers = {doc_type: generic for doc_type in DocumentType.ALL}
    readers[DocumentType.FOLIO] = get_folio_extractor()
    readers[DocumentType.TAX_RECEIPT] = get_tax_extractor()
    return readers


def run_server_reading(document_id: str, user_sub: str) -> None:
    """Entry point for the background reading of a folio or a tax receipt. Runs
    after the `analyze` request returned, so the request's session is already
    closed -- it opens and closes its own, like the folios domain's pipeline."""
    db = SessionLocal()
    try:
        RunServerReadingUseCase(
            documents=SqlDocumentRepository(db),
            captures=SqlCaptureRepository(db),
            extractors=get_server_readers(),
            folders=SqlRegisteredFolderRepository(db),
        ).execute(document_id, user_sub)
    finally:
        db.close()


def get_synchronizer(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    queue: ExtractionQueuePort = Depends(get_queue),
) -> DocumentSynchronizer:
    return DocumentSynchronizer(documents, queue)


def get_upload_captures_use_case(
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> UploadCapturesUseCase:
    return UploadCapturesUseCase(captures, get_thumbnails(), get_pdf_rasterizer())


def get_list_inbox_use_case(captures: CaptureRepositoryPort = Depends(get_capture_repository)) -> ListInboxUseCase:
    return ListInboxUseCase(captures)


def get_capture_image_use_case(
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> GetCaptureImageUseCase:
    return GetCaptureImageUseCase(captures, get_thumbnails())


def get_delete_capture_use_case(
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> DeleteCaptureUseCase:
    return DeleteCaptureUseCase(captures)


def get_clear_inbox_use_case(
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> ClearInboxUseCase:
    return ClearInboxUseCase(captures)


def get_create_document_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
) -> CreateDocumentUseCase:
    return CreateDocumentUseCase(documents, captures, folders)


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


def get_list_reviewed_documents_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
) -> ListReviewedDocumentsUseCase:
    return ListReviewedDocumentsUseCase(documents)


def get_review_document_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
) -> ReviewDocumentUseCase:
    return ReviewDocumentUseCase(documents)


# --------------------------------------------------------- carpetas registradas


def get_registered_folder_service(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
    documents: DocumentRepositoryPort = Depends(get_document_repository),
) -> RegisteredFolderService:
    """The rules every carpeta write shares (free name, filable documents)."""
    return RegisteredFolderService(folders, documents)


def get_list_registered_folders_use_case(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
) -> ListRegisteredFoldersUseCase:
    return ListRegisteredFoldersUseCase(folders)


def get_get_registered_folder_use_case(
    service: RegisteredFolderService = Depends(get_registered_folder_service),
) -> GetRegisteredFolderUseCase:
    return GetRegisteredFolderUseCase(service)


def get_create_registered_folder_use_case(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
    service: RegisteredFolderService = Depends(get_registered_folder_service),
) -> CreateRegisteredFolderUseCase:
    return CreateRegisteredFolderUseCase(folders, service)


def get_update_registered_folder_use_case(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
    service: RegisteredFolderService = Depends(get_registered_folder_service),
) -> UpdateRegisteredFolderUseCase:
    return UpdateRegisteredFolderUseCase(folders, service)


def get_add_folder_documents_use_case(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
    service: RegisteredFolderService = Depends(get_registered_folder_service),
) -> AddDocumentsToRegisteredFolderUseCase:
    return AddDocumentsToRegisteredFolderUseCase(folders, service)


def get_remove_folder_document_use_case(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
    service: RegisteredFolderService = Depends(get_registered_folder_service),
) -> RemoveDocumentFromRegisteredFolderUseCase:
    return RemoveDocumentFromRegisteredFolderUseCase(folders, service)


def get_delete_registered_folder_use_case(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
    service: RegisteredFolderService = Depends(get_registered_folder_service),
) -> DeleteRegisteredFolderUseCase:
    return DeleteRegisteredFolderUseCase(folders, service)


@lru_cache()
def get_cadastral_gis() -> CadastralGisPort:
    return ArcGisCadastralGis()


def get_lookup_cadastral_parcel_use_case(
    gis: CadastralGisPort = Depends(get_cadastral_gis),
) -> LookupCadastralParcelUseCase:
    return LookupCadastralParcelUseCase(gis)


def get_generate_cadastral_croquis_use_case(
    gis: CadastralGisPort = Depends(get_cadastral_gis),
) -> GenerateCadastralCroquisUseCase:
    return GenerateCadastralCroquisUseCase(gis)
