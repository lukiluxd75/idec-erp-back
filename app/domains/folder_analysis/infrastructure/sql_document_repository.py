from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, undefer

from app.domains.folder_analysis.domain.entities import (
    DocumentPage,
    DocumentStatus,
    FolderDocument,
    PageStatus,
)
from app.domains.folder_analysis.domain.ports import DocumentRepositoryPort
from app.domains.folder_analysis.infrastructure.models import (
    DocumentModel,
    DocumentPageModel,
    RegisteredFolderItemModel,
    ReviewedFolioModel,
    ReviewedPlanModel,
    ReviewedTaxReceiptModel,
)
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
        folder_type=row.folder_type,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        pages=[_to_page(p) for p in row.pages],
        folder_id=str(row.folder_item.folder_id) if row.folder_item else None,
        extracted_data=row.extracted_data if with_data else None,
        reviewed_data=row.reviewed_data if with_data else None,
        error=row.error,
        stage=row.stage,
        analyzed_at=row.analyzed_at,
        reviewed_at=row.reviewed_at,
    )


def _new_pages(capture_ids: List[str]) -> List[DocumentPageModel]:
    return [
        DocumentPageModel(capture_id=parse_uuid(capture_id), page_index=index, status=PageStatus.DRAFT)
        for index, capture_id in enumerate(capture_ids)
    ]


def _delete_reviewed_snapshots(db: Session, document_id: Any) -> None:
    for model in (ReviewedFolioModel, ReviewedTaxReceiptModel, ReviewedPlanModel):
        db.execute(delete(model).where(model.document_id == document_id))


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

    def create(
        self,
        user_sub: str,
        doc_type: str,
        capture_ids: List[str],
        folder_type: Optional[str] = None,
    ) -> FolderDocument:
        row = DocumentModel(
            user_sub=user_sub,
            doc_type=doc_type,
            folder_type=folder_type,
            status=DocumentStatus.DRAFT,
        )
        row.pages = _new_pages(capture_ids)
        self._db.add(row)
        self._db.commit()
        return self.get(str(row.id), user_sub)

    def get(self, document_id: str, user_sub: str) -> Optional[FolderDocument]:
        row = self._row(document_id, with_data=True)
        if row is None or row.user_sub != user_sub:
            return None
        return _to_entity(row, with_data=True)

    def _filtered(self, query, doc_type: Optional[str], folder_id: Optional[str]):
        """The two filters both listings share. Narrowing by carpeta joins the
        rows that file the documents: which carpeta holds a document is stored
        there and nowhere else. An id that is not a uuid matches nothing, which
        is what a carpeta that does not exist should show."""
        if doc_type:
            query = query.where(DocumentModel.doc_type == doc_type)
        if folder_id:
            query = query.join(
                RegisteredFolderItemModel,
                RegisteredFolderItemModel.document_id == DocumentModel.id,
            ).where(RegisteredFolderItemModel.folder_id == parse_uuid(folder_id))
        return query

    def list(
        self,
        user_sub: str,
        doc_type: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> List[FolderDocument]:
        query = self._filtered(
            select(DocumentModel).where(DocumentModel.user_sub == user_sub), doc_type, folder_id
        )
        rows = self._db.execute(query.order_by(DocumentModel.created_at.desc())).scalars()
        return [_to_entity(row, with_data=False) for row in rows]

    def list_reviewed(
        self,
        user_sub: str,
        doc_type: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> List[FolderDocument]:
        query = self._filtered(
            select(DocumentModel)
            .where(DocumentModel.user_sub == user_sub, DocumentModel.status == DocumentStatus.REVIEWED)
            .options(undefer(DocumentModel.extracted_data), undefer(DocumentModel.reviewed_data)),
            doc_type,
            folder_id,
        )
        rows = self._db.execute(query.order_by(DocumentModel.reviewed_at.desc())).scalars()
        return [_to_entity(row, with_data=True) for row in rows]

    def replace_pages(self, document_id: str, capture_ids: List[str]) -> None:
        row = self._row(document_id, with_data=True)
        row.pages.clear()
        self._db.flush()
        row.pages.extend(_new_pages(capture_ids))
        row.status = DocumentStatus.DRAFT
        row.extracted_data = None
        row.reviewed_data = None
        row.error = None
        row.analyzed_at = None
        row.reviewed_at = None
        _delete_reviewed_snapshots(self._db, row.id)
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
        _delete_reviewed_snapshots(self._db, row.id)
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
        if status not in DocumentStatus.IN_PROGRESS:
            row.stage = None
        if extracted_data is not None:
            row.extracted_data = extracted_data
        self._db.commit()

    def set_stage(self, document_id: str, stage: Optional[str]) -> None:
        row = self._row(document_id)
        if row is None:
            return
        row.stage = stage
        self._db.commit()

    def save_review(self, document_id: str, data: Dict[str, Any]) -> None:
        row = self._row(document_id, with_data=True)
        reviewed_at = _now()
        row.reviewed_data = data
        row.status = DocumentStatus.REVIEWED
        row.reviewed_at = reviewed_at
        # Keep one typed, queryable row per reviewed source document.
        _delete_reviewed_snapshots(self._db, row.id)

        if row.doc_type == "folio":
            page = data.get("page") if isinstance(data.get("page"), dict) else {}
            self._db.add(ReviewedFolioModel(
                document_id=row.id,
                user_sub=row.user_sub,
                registration_number=data.get("registration_number"),
                registration_status=data.get("registration_status"),
                administrative_location=data.get("administrative_location"),
                cadastre=data.get("cadastre"),
                property_type=data.get("property_type"),
                location=data.get("location"),
                designation=data.get("designation"),
                surface=data.get("surface"),
                measures=data.get("measures"),
                boundaries=data.get("boundaries") if isinstance(data.get("boundaries"), dict) else {},
                property_description=data.get("property"),
                prior_title=data.get("prior_title"),
                document_date=data.get("date"),
                page_number=_optional_int(page.get("number")),
                page_total=_optional_int(page.get("total")),
                ownership_entries=data.get("ownership_entries") if isinstance(data.get("ownership_entries"), list) else [],
                reviewed_data=data,
                reviewed_at=reviewed_at,
            ))
        elif row.doc_type == "tax_receipt":
            taxpayer = data.get("taxpayer") if isinstance(data.get("taxpayer"), dict) else {}
            self._db.add(ReviewedTaxReceiptModel(
                document_id=row.id,
                user_sub=row.user_sub,
                **{key: data.get(key) for key in (
                    "receipt_type", "receipt_number", "municipality", "paid_at", "collecting_entity",
                    "correspondent", "branch", "agency", "cashier", "folio", "concept", "property_number",
                    "cadastral_code", "property_class", "ownership_type", "location", "land_area", "built_area",
                    "age_factor", "ufv", "taxable_base", "assessed_tax", "exemption", "discount_10",
                    "discount_app_5", "amount_due", "amount_paid", "balance",
                )},
                tax_year=_optional_int(data.get("tax_year")),
                taxpayer_type=taxpayer.get("type"),
                taxpayer_id_number=taxpayer.get("id_number"),
                taxpayer_name=taxpayer.get("name"),
                reviewed_data=data,
                reviewed_at=reviewed_at,
            ))
        elif row.doc_type == "plan":
            self._db.add(ReviewedPlanModel(
                document_id=row.id,
                user_sub=row.user_sub,
                plan_name=data.get("plan_name") or data.get("name") or data.get("title"),
                plan_type=data.get("plan_type") or data.get("type"),
                address=data.get("address") or data.get("location"),
                cadastral_code=data.get("cadastral_code") or data.get("cadastre"),
                scale=data.get("scale"),
                plan_date=data.get("plan_date") or data.get("date"),
                extracted_data=row.extracted_data if isinstance(row.extracted_data, dict) else {},
                reviewed_data=data,
                reviewed_at=reviewed_at,
            ))
        self._db.commit()


def _optional_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
