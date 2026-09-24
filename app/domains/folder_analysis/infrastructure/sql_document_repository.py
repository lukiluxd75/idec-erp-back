from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app.domains.folder_analysis.domain.entities import (
    DocumentPage,
    DocumentStatus,
    FolderDocument,
    PageStatus,
)
from app.domains.folder_analysis.domain.ports import DocumentRepositoryPort
from app.domains.folder_analysis.infrastructure.models import DocumentModel, DocumentPageModel
from app.domains.folder_analysis.infrastructure.sql_capture_repository import parse_uuid


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_page(row: DocumentPageModel) -> DocumentPage:
    return DocumentPage(
        capture_id=str(row.capture_id),
        page_index=row.page_index,
        status=row.status,
        job_id=row.job_id,
        result=row.result,
        error=row.error,
    )


def _to_entity(row: DocumentModel, with_data: bool) -> FolderDocument:
    return FolderDocument(
        id=str(row.id),
        user_sub=row.user_sub,
        doc_type=row.doc_type,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        pages=[_to_page(p) for p in row.pages],
        extracted_data=row.extracted_data if with_data else None,
        reviewed_data=row.reviewed_data if with_data else None,
        error=row.error,
        analyzed_at=row.analyzed_at,
        reviewed_at=row.reviewed_at,
    )


def _new_pages(capture_ids: List[str]) -> List[DocumentPageModel]:
    return [
        DocumentPageModel(capture_id=parse_uuid(capture_id), page_index=index, status=PageStatus.DRAFT)
        for index, capture_id in enumerate(capture_ids)
    ]


class SqlDocumentRepository(DocumentRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def _row(self, document_id: str, with_data: bool = False) -> Optional[DocumentModel]:
        parsed = parse_uuid(document_id)
        if parsed is None:
            return None
        query = select(DocumentModel).where(DocumentModel.id == parsed)
        if with_data:
            query = query.options(undefer(DocumentModel.extracted_data), undefer(DocumentModel.reviewed_data))
        return self._db.execute(query).scalar_one_or_none()

    def create(self, user_sub: str, doc_type: str, capture_ids: List[str]) -> FolderDocument:
        row = DocumentModel(user_sub=user_sub, doc_type=doc_type, status=DocumentStatus.DRAFT)
        row.pages = _new_pages(capture_ids)
        self._db.add(row)
        self._db.commit()
        return self.get(str(row.id), user_sub)

    def get(self, document_id: str, user_sub: str) -> Optional[FolderDocument]:
        row = self._row(document_id, with_data=True)
        if row is None or row.user_sub != user_sub:
            return None
        return _to_entity(row, with_data=True)

    def list(self, user_sub: str, doc_type: Optional[str] = None) -> List[FolderDocument]:
        query = select(DocumentModel).where(DocumentModel.user_sub == user_sub)
        if doc_type:
            query = query.where(DocumentModel.doc_type == doc_type)
        rows = self._db.execute(query.order_by(DocumentModel.created_at.desc())).scalars()
        return [_to_entity(row, with_data=False) for row in rows]

    def replace_pages(self, document_id: str, capture_ids: List[str]) -> None:
        row = self._row(document_id, with_data=True)
        # Flush the removal first: the (document_id, page_index) and capture_id
        # unique constraints would clash with the new rows otherwise.
        row.pages.clear()
        self._db.flush()
        row.pages.extend(_new_pages(capture_ids))
        row.status = DocumentStatus.DRAFT
        row.extracted_data = None
        row.reviewed_data = None
        row.error = None
        row.analyzed_at = None
        row.reviewed_at = None
        self._db.commit()

    def delete(self, document_id: str) -> None:
        row = self._row(document_id)
        if row is not None:
            self._db.delete(row)
            self._db.commit()

    def mark_submitted(self, document_id: str, job_ids_by_page: Dict[int, str]) -> None:
        row = self._row(document_id, with_data=True)
        for page in row.pages:
            page.status = PageStatus.QUEUED
            page.job_id = job_ids_by_page.get(page.page_index)
            page.result = None
            page.error = None
        row.status = DocumentStatus.QUEUED
        row.extracted_data = None
        row.reviewed_data = None
        row.error = None
        row.analyzed_at = _now()
        row.reviewed_at = None
        self._db.commit()

    def save_progress(
        self,
        document_id: str,
        pages: List[DocumentPage],
        status: str,
        extracted_data: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> None:
        row = self._row(document_id, with_data=True)
        by_index = {p.page_index: p for p in pages}
        for page_row in row.pages:
            page = by_index.get(page_row.page_index)
            if page is not None:
                page_row.status, page_row.result, page_row.error = page.status, page.result, page.error
        row.status = status
        row.error = error
        if extracted_data is not None:
            row.extracted_data = extracted_data
        self._db.commit()

    def save_review(self, document_id: str, data: Dict[str, Any]) -> None:
        row = self._row(document_id, with_data=True)
        row.reviewed_data = data
        row.status = DocumentStatus.REVIEWED
        row.reviewed_at = _now()
        self._db.commit()
