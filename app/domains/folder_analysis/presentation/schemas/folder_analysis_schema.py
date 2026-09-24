from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.domains.folder_analysis.domain.entities import Capture, FolderDocument

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
