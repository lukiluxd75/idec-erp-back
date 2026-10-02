import logging
from functools import lru_cache
from typing import Dict

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database.connection import SessionLocal, get_db
from app.core.presence import (
    CHANNEL_FOLDER_ANALYSIS,
    SqlPresenceStore,
    device_id_for_request,
)
from app.core.utils.user_agent import looks_like_phone
from app.domains.security.contracts import UserProfile, get_current_user
from app.domains.digitization.contracts import get_borrow_host, get_worker_host_picker
from app.domains.folder_analysis.application.document_synchronizer import DocumentSynchronizer
from app.domains.folder_analysis.application.use_cases import (
    AddDocumentsToRegisteredFolderUseCase,
    AnalyzeDocumentUseCase,
    ConsolidateDocumentsUseCase,
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
    SaveBoardToFolderUseCase,
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
    readers = {doc_type: generic for doc_type in DocumentType.SERVER_READ}
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


def get_consolidate_documents_use_case(
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
) -> ConsolidateDocumentsUseCase:
    return ConsolidateDocumentsUseCase(documents, captures, folders)


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


def get_save_board_to_folder_use_case(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    service: RegisteredFolderService = Depends(get_registered_folder_service),
) -> SaveBoardToFolderUseCase:
    return SaveBoardToFolderUseCase(folders, documents, service)


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
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> RemoveDocumentFromRegisteredFolderUseCase:
    return RemoveDocumentFromRegisteredFolderUseCase(folders, service, documents, captures)


def get_delete_registered_folder_use_case(
    folders: RegisteredFolderRepositoryPort = Depends(get_registered_folder_repository),
    service: RegisteredFolderService = Depends(get_registered_folder_service),
    documents: DocumentRepositoryPort = Depends(get_document_repository),
    captures: CaptureRepositoryPort = Depends(get_capture_repository),
) -> DeleteRegisteredFolderUseCase:
    return DeleteRegisteredFolderUseCase(folders, service, documents, captures)


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


# --- "Celular conectado" -------------------------------------------------------
#
# Este dominio no tiene websocket (ver usePollWhile.js y el contrato en
# docs/FOLDER_ANALYSIS_API_MOVIL.md: la app solo hace POST /captures), así que su
# presencia es del tipo "actividad": cada petición que llega desde un celular
# refresca la fila. El estado vive en Postgres, no en memoria del proceso, para
# que los 4 workers respondan lo mismo -- ver app/core/presence.


def get_presence_store(db: Session = Depends(get_db)) -> SqlPresenceStore:
    """Sesión por petición, no singleton: el estado es compartido, no del proceso."""
    return SqlPresenceStore(db=db)


def record_mobile_presence(
    request: Request,
    user: UserProfile = Depends(get_current_user),
    presence: SqlPresenceStore = Depends(get_presence_store),
) -> None:
    """Marca "celular conectado" cuando la petición viene de un celular.

    Se cuelga de los endpoints que la app móvil usa. El filtro por User-Agent es
    lo que impide que una subida hecha desde el escritorio (el arquitecto puede
    arrastrar archivos, ver captureUpload.js) encienda el indicador.

    Depende de `get_current_user` y no de `require_permission` a propósito: el
    endpoint al que se engancha ya exige su permiso, y repetirlo aquí solo
    duplicaría la consulta de permisos en cada subida.
    """
    user_agent = request.headers.get("user-agent", "")
    # looks_like_phone y no is_mobile_user_agent: ese solo reconoce NAVEGADORES
    # de celular, y la app movil es nativa -- manda `okhttp/4.12.0` o
    # `Dart/3.3 (dart:io)`, que no contienen "Mobi" ni "Android". Por eso la
    # foto llegaba pero el indicador nunca se encendia.
    if not looks_like_phone(user_agent):
        # Se registra el User-Agent descartado porque este indicador falla
        # callado por naturaleza: si no se enciende, no hay nada en pantalla
        # que diga por que. Con esta linea, una subida que el servidor tomo por
        # escritorio deja constancia de con que se identifico.
        logging.getLogger("uvicorn.error").info(
            "presence: subida a folder-analysis tomada como escritorio, "
            "no enciende el indicador. User-Agent=%r",
            user_agent,
        )
        return
    presence.touch_activity(
        user.sub,
        CHANNEL_FOLDER_ANALYSIS,
        device_id_for_request(user.sub, user_agent),
    )
