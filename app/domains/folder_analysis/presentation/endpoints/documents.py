import json
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, Response, status

from app.domains.folder_analysis.application.use_cases import (
    AnalyzeDocumentUseCase,
    CreateDocumentUseCase,
    DeleteDocumentUseCase,
    GetDocumentUseCase,
    ListDocumentsUseCase,
    ListReviewedDocumentsUseCase,
    ReviewDocumentUseCase,
    SetDocumentPagesUseCase,
)
from app.domains.folder_analysis.domain.entities import DocumentType
from app.domains.folder_analysis.presentation.deps import (
    get_analyze_document_use_case,
    get_create_document_use_case,
    get_delete_document_use_case,
    get_get_document_use_case,
    get_list_documents_use_case,
    get_list_reviewed_documents_use_case,
    get_review_document_use_case,
    get_set_pages_use_case,
    run_server_reading,
)
from app.domains.folder_analysis.presentation.schemas.folder_analysis_schema import (
    AnalyzeRequest,
    CreateDocumentRequest,
    DocType,
    DocumentDetail,
    DocumentSummary,
    ReviewRequest,
    SetPagesRequest,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/documents", tags=["Folder analysis · Documents"])


@router.post("", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
def create_document(
    body: CreateDocumentRequest,
    use_case: CreateDocumentUseCase = Depends(get_create_document_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Photos dropped onto a lane, in page order. With `folder_id`, the document
    is opened inside that carpeta and has to be one of the types it holds."""
    document = use_case.execute(
        body.doc_type, body.capture_ids, user.sub, body.folder_id, body.folder_type
    )
    return DocumentDetail.from_entity(document)


@router.get("", response_model=List[DocumentSummary])
def list_documents(
    doc_type: Optional[DocType] = Query(None),
    folder_id: Optional[str] = Query(None, description="Solo los documentos de esa carpeta."),
    use_case: ListDocumentsUseCase = Depends(get_list_documents_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """The user's documents, newest first. Refreshes the ones being analyzed.

    With `folder_id`, only the ones worked on inside that carpeta -- which is
    what its board shows."""
    return [DocumentSummary.from_entity(d) for d in use_case.execute(user.sub, doc_type, folder_id)]


@router.get("/reviewed", response_model=List[DocumentDetail])
def list_reviewed_documents(
    doc_type: Optional[DocType] = Query(None),
    folder_id: Optional[str] = Query(None, description="Solo los documentos de esa carpeta."),
    use_case: ListReviewedDocumentsUseCase = Depends(get_list_reviewed_documents_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Saved reviews only, with the confirmed data for the current user."""
    return [DocumentDetail.from_entity(d) for d in use_case.execute(user.sub, doc_type, folder_id)]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: str,
    use_case: GetDocumentUseCase = Depends(get_get_document_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    return DocumentDetail.from_entity(use_case.execute(document_id, user.sub))


@router.put("/{document_id}/pages", response_model=DocumentDetail)
def set_pages(
    document_id: str,
    body: SetPagesRequest,
    use_case: SetDocumentPagesUseCase = Depends(get_set_pages_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """New page list (add, remove, reorder). Discards any previous result."""
    return DocumentDetail.from_entity(use_case.execute(document_id, body.capture_ids, user.sub))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    use_case: DeleteDocumentUseCase = Depends(get_delete_document_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Deletes the document; its photos go back to the inbox."""
    use_case.execute(document_id, user.sub)


@router.post("/{document_id}/analyze", response_model=DocumentDetail, status_code=status.HTTP_202_ACCEPTED)
def analyze_document(
    document_id: str,
    background: BackgroundTasks,
    body: AnalyzeRequest = Body(default_factory=AnalyzeRequest),
    use_case: AnalyzeDocumentUseCase = Depends(get_analyze_document_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Starts the analysis. Returns right away; poll GET.

    A folio and a tax receipt are read here on the server (OCR + rules, seconds);
    a plan goes to the architects' PCs through the digitization queue."""
    document = use_case.execute(document_id, user.sub, body.force)
    if document.doc_type in DocumentType.SERVER_READ:
        background.add_task(run_server_reading, document_id, user.sub)
    return DocumentDetail.from_entity(document)


@router.put("/{document_id}/review", response_model=DocumentDetail)
def review_document(
    document_id: str,
    body: ReviewRequest,
    use_case: ReviewDocumentUseCase = Depends(get_review_document_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Saves the architect's corrected JSON."""
    return DocumentDetail.from_entity(use_case.execute(document_id, user.sub, body.data))


@router.get("/{document_id}/export")
def export_document(
    document_id: str,
    use_case: GetDocumentUseCase = Depends(get_get_document_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """The document's current data (reviewed if saved, otherwise extracted) as a .json file."""
    document = use_case.execute(document_id, user.sub)
    payload = {
        "document_id": document.id,
        "doc_type": document.doc_type,
        "status": document.status,
        "analyzed_at": document.analyzed_at.isoformat() if document.analyzed_at else None,
        "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
        "data": document.current_data,
    }
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{document.doc_type}-{document.id[:8]}.json"'},
    )
