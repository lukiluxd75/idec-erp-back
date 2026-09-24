from typing import Any, Dict, List, Optional

from app.domains.folder_analysis.application.document_synchronizer import DocumentSynchronizer
from app.domains.folder_analysis.domain.entities import CaptureStatus, DocumentStatus, DocumentType, FolderDocument
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotAvailableException,
    CaptureNotFoundException,
    DocumentBusyException,
    DocumentNotFoundException,
    InvalidDocumentRequestException,
)
from app.domains.folder_analysis.domain.extraction_profiles import PROFILES
from app.domains.folder_analysis.domain.ports import CaptureRepositoryPort, DocumentRepositoryPort, ExtractionQueuePort

MAX_PAGES = 10


def _require_document(repository: DocumentRepositoryPort, document_id: str, user_sub: str) -> FolderDocument:
    document = repository.get(document_id, user_sub)
    if document is None:
        raise DocumentNotFoundException()
    return document


def _validate_capture_ids(capture_ids: List[str]) -> List[str]:
    unique = list(dict.fromkeys(capture_ids or []))
    if not unique:
        raise InvalidDocumentRequestException("El documento debe tener al menos una foto.")
    if len(unique) > MAX_PAGES:
        raise InvalidDocumentRequestException(f"Un documento admite como máximo {MAX_PAGES} fotos.")
    return unique


def _require_inbox_captures(captures: CaptureRepositoryPort, capture_ids: List[str], user_sub: str) -> None:
    found = {c.id: c for c in captures.get_many(capture_ids, user_sub)}
    if len(found) != len(capture_ids):
        raise CaptureNotFoundException("Una de las fotos no existe o no le pertenece.")
    if any(c.status != CaptureStatus.INBOX for c in found.values()):
        raise CaptureNotAvailableException("Una de las fotos ya forma parte de otro documento.")


class CreateDocumentUseCase:
    """The architect dropped photos onto one of the three sections."""

    def __init__(self, documents: DocumentRepositoryPort, captures: CaptureRepositoryPort):
        self._documents = documents
        self._captures = captures

    def execute(self, doc_type: str, capture_ids: List[str], user_sub: str) -> FolderDocument:
        if doc_type not in DocumentType.ALL:
            raise InvalidDocumentRequestException("El tipo de documento no es válido.")
        ids = _validate_capture_ids(capture_ids)
        _require_inbox_captures(self._captures, ids, user_sub)
        document = self._documents.create(user_sub, doc_type, ids)
        self._captures.set_status(ids, CaptureStatus.ASSIGNED)
        return document


class SetDocumentPagesUseCase:
    """Add, remove or reorder pages. Changing pages discards any previous result,
    so it is not allowed while the document is being analyzed."""

    def __init__(self, documents: DocumentRepositoryPort, captures: CaptureRepositoryPort):
        self._documents = documents
        self._captures = captures

    def execute(self, document_id: str, capture_ids: List[str], user_sub: str) -> FolderDocument:
        document = _require_document(self._documents, document_id, user_sub)
        if document.status in DocumentStatus.IN_PROGRESS:
            raise DocumentBusyException("El documento se está analizando; espere a que termine para cambiar sus fotos.")
        ids = _validate_capture_ids(capture_ids)
        current = [p.capture_id for p in document.pages]
        added = [c for c in ids if c not in current]
        removed = [c for c in current if c not in ids]
        if added:
            _require_inbox_captures(self._captures, added, user_sub)
        self._documents.replace_pages(document_id, ids)
        self._captures.set_status(added, CaptureStatus.ASSIGNED)
        self._captures.set_status(removed, CaptureStatus.INBOX)
        return _require_document(self._documents, document_id, user_sub)


class DeleteDocumentUseCase:
    """Removes the document; its photos go back to the inbox."""

    def __init__(self, documents: DocumentRepositoryPort, captures: CaptureRepositoryPort):
        self._documents = documents
        self._captures = captures

    def execute(self, document_id: str, user_sub: str) -> None:
        document = _require_document(self._documents, document_id, user_sub)
        self._documents.delete(document_id)
        self._captures.set_status([p.capture_id for p in document.pages], CaptureStatus.INBOX)


class AnalyzeDocumentUseCase:
    """Sends every page to the PCs with the extraction profile of its type."""

    def __init__(
        self, documents: DocumentRepositoryPort, captures: CaptureRepositoryPort, queue: ExtractionQueuePort
    ):
        self._documents = documents
        self._captures = captures
        self._queue = queue

    def execute(self, document_id: str, user_sub: str, force: bool = False) -> FolderDocument:
        document = _require_document(self._documents, document_id, user_sub)
        if document.status in DocumentStatus.IN_PROGRESS:
            raise DocumentBusyException("El documento ya se está analizando.")
        if document.status == DocumentStatus.REVIEWED and not force:
            raise DocumentBusyException(
                "El documento ya fue revisado. Si lo vuelve a analizar se perderán sus correcciones; confirme para continuar."
            )

        profile = PROFILES[document.doc_type]
        job_ids: Dict[int, str] = {}
        for page in document.pages:
            image = self._captures.get_image(page.capture_id, user_sub)
            if image is None:
                raise CaptureNotFoundException(f"No se encontró la foto de la página {page.page_index + 1}.")
            content, mime = image
            job_ids[page.page_index] = self._queue.submit(
                content=content,
                file_name=f"{document.doc_type}-{document.id[:8]}-p{page.page_index + 1}.jpg",
                mime_type=mime,
                requested_by=user_sub,
                instructions=profile.instructions,
                output_template=profile.output_template,
            )
        self._documents.mark_submitted(document_id, job_ids)
        return _require_document(self._documents, document_id, user_sub)


class GetDocumentUseCase:
    def __init__(self, documents: DocumentRepositoryPort, synchronizer: DocumentSynchronizer):
        self._documents = documents
        self._synchronizer = synchronizer

    def execute(self, document_id: str, user_sub: str) -> FolderDocument:
        document = _require_document(self._documents, document_id, user_sub)
        return self._synchronizer.refresh([document])[0]


class ListDocumentsUseCase:
    def __init__(self, documents: DocumentRepositoryPort, synchronizer: DocumentSynchronizer):
        self._documents = documents
        self._synchronizer = synchronizer

    def execute(self, user_sub: str, doc_type: Optional[str] = None) -> List[FolderDocument]:
        if doc_type is not None and doc_type not in DocumentType.ALL:
            raise InvalidDocumentRequestException("El tipo de documento no es válido.")
        return self._synchronizer.refresh(self._documents.list(user_sub, doc_type))


class ReviewDocumentUseCase:
    """Saves the architect's corrected data (kept next to the extracted version)."""

    def __init__(self, documents: DocumentRepositoryPort):
        self._documents = documents

    def execute(self, document_id: str, user_sub: str, data: Dict[str, Any]) -> FolderDocument:
        document = _require_document(self._documents, document_id, user_sub)
        if document.status in (DocumentStatus.DRAFT, *DocumentStatus.IN_PROGRESS):
            raise DocumentBusyException("Solo puede revisar un documento que ya fue analizado.")
        if not isinstance(data, dict) or not data:
            raise InvalidDocumentRequestException("Los datos del documento están vacíos.")
        self._documents.save_review(document_id, data)
        return _require_document(self._documents, document_id, user_sub)
