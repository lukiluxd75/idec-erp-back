from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.domains.folder_analysis.domain.entities import (
    MAX_NAME_LENGTH,
    MAX_NOTES_LENGTH,
    Capture,
    FolderDocument,
    RegisteredFolder,
)

DocType = Literal["folio", "tax_receipt", "plan"]


class CaptureOut(BaseModel):
    id: str
    file_name: str
    status: str
    created_at: datetime

    @classmethod
    def from_entity(cls, capture: Capture) -> "CaptureOut":
        return cls(id=capture.id, file_name=capture.file_name, status=capture.status, created_at=capture.created_at)


class PageOut(BaseModel):
    capture_id: str
    page_index: int
    status: str
    error: Optional[str] = None


class DocumentSummary(BaseModel):
    id: str
    doc_type: str
    status: str
    pages: List[PageOut]
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    analyzed_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None

    @classmethod
    def from_entity(cls, document: FolderDocument) -> "DocumentSummary":
        return cls(
            id=document.id,
            doc_type=document.doc_type,
            status=document.status,
            pages=[
                PageOut(capture_id=p.capture_id, page_index=p.page_index, status=p.status, error=p.error)
                for p in document.pages
            ],
            error=document.error,
            created_at=document.created_at,
            updated_at=document.updated_at,
            analyzed_at=document.analyzed_at,
            reviewed_at=document.reviewed_at,
        )


class DocumentDetail(DocumentSummary):
    extracted_data: Optional[Dict[str, Any]] = None
    reviewed_data: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None

    @classmethod
    def from_entity(cls, document: FolderDocument) -> "DocumentDetail":
        return cls(
            **DocumentSummary.from_entity(document).model_dump(),
            extracted_data=document.extracted_data,
            reviewed_data=document.reviewed_data,
            data=document.current_data,
        )


class CreateDocumentRequest(BaseModel):
    doc_type: DocType
    capture_ids: List[str] = Field(min_length=1)


class SetPagesRequest(BaseModel):
    capture_ids: List[str] = Field(min_length=1)


class AnalyzeRequest(BaseModel):
    force: bool = False


class ReviewRequest(BaseModel):
    data: Dict[str, Any]


# ---------------------------------------------------------- carpetas registradas


class RegisteredFolderOut(BaseModel):
    """A project folder with the documents filed in it, data included: the
    screen lists a carpeta and its saved documents in one read."""

    id: str
    name: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentDetail]
    document_count: int
    counts_by_type: Dict[str, int]

    @classmethod
    def from_entity(cls, folder: RegisteredFolder) -> "RegisteredFolderOut":
        return cls(
            id=folder.id,
            name=folder.name,
            notes=folder.notes,
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            documents=[DocumentDetail.from_entity(d) for d in folder.documents],
            document_count=len(folder.documents),
            counts_by_type=folder.counts_by_type,
        )


class CreateRegisteredFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    notes: Optional[str] = Field(default=None, max_length=MAX_NOTES_LENGTH)
    document_ids: List[str] = Field(default_factory=list)


class UpdateRegisteredFolderRequest(BaseModel):
    """`document_ids` left out keeps the carpeta's contents as they are; sent, it
    becomes the whole content (an empty list empties the carpeta)."""

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    notes: Optional[str] = Field(default=None, max_length=MAX_NOTES_LENGTH)
    document_ids: Optional[List[str]] = None


class AddRegisteredFolderDocumentsRequest(BaseModel):
    document_ids: List[str] = Field(min_length=1)
