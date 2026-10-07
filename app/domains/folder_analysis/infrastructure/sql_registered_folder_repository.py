from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, undefer

from app.domains.folder_analysis.domain.entities import RegisteredFolder
from app.domains.folder_analysis.domain.ports import RegisteredFolderRepositoryPort
from app.domains.folder_analysis.infrastructure.models import (
    DocumentModel,
    RegisteredFolderItemModel,
    RegisteredFolderModel,
)
from app.domains.folder_analysis.infrastructure.sql_capture_repository import parse_uuid
from app.domains.folder_analysis.infrastructure.sql_document_repository import (
    _to_entity as _to_document_entity,
)


class SqlRegisteredFolderRepository(RegisteredFolderRepositoryPort):
    """The carpetas and their items. A carpeta is read together with the saved
    data of the documents it holds, which is what the screen lists."""

    def __init__(self, db: Session):
        self._db = db

    # ------------------------------------------------------------------ reading

    def _row(self, folder_id: str) -> Optional[RegisteredFolderModel]:
        parsed = parse_uuid(folder_id)
        if parsed is None:
            return None
        return self._db.execute(
            select(RegisteredFolderModel).where(RegisteredFolderModel.id == parsed)
        ).scalar_one_or_none()

    def _documents_by_id(self, document_ids: List[str]) -> Dict[str, DocumentModel]:
        """The filed documents in one query, with their data undeferred."""
        if not document_ids:
            return {}
        rows = self._db.execute(
            select(DocumentModel)
            .where(DocumentModel.id.in_([parse_uuid(i) for i in document_ids]))
            .options(undefer(DocumentModel.extracted_data), undefer(DocumentModel.reviewed_data))
        ).scalars()
        return {str(row.id): row for row in rows}

    def _to_entity(self, row: RegisteredFolderModel, with_documents: bool = True) -> RegisteredFolder:
        ids = [str(item.document_id) for item in row.items] if with_documents else []
        documents = self._documents_by_id(ids)
        return RegisteredFolder(
            id=str(row.id),
            user_sub=row.user_sub,
            name=row.name,
            notes=row.notes,
            folder_type=row.folder_type,
            data=row.data or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
            # Filing order, skipping anything deleted between the two queries.
            documents=[_to_document_entity(documents[i], with_data=True) for i in ids if i in documents],
        )

    def get(self, folder_id: str, user_sub: str) -> Optional[RegisteredFolder]:
        row = self._row(folder_id)
        if row is None or row.user_sub != user_sub:
            return None
        return self._to_entity(row)

    def find_any(self, folder_id: str) -> Optional[RegisteredFolder]:
        row = self._row(folder_id)
        return None if row is None else self._to_entity(row)

    def list_sheets(self, user_sub: str) -> List[RegisteredFolder]:
        # Sin la consulta de los documentos: la hoja de la carpeta es su propia fila (su puerto lo dice).
        rows = self._db.execute(
            select(RegisteredFolderModel)
            .where(RegisteredFolderModel.user_sub == user_sub)
            .order_by(func.lower(RegisteredFolderModel.name))
        ).scalars()
        return [self._to_entity(row, with_documents=False) for row in rows]

    def list(self, user_sub: str) -> List[RegisteredFolder]:
        rows = self._db.execute(
            select(RegisteredFolderModel)
            .where(RegisteredFolderModel.user_sub == user_sub)
            .order_by(func.lower(RegisteredFolderModel.name))
        ).scalars()
        return [self._to_entity(row) for row in rows]

    def search_by_name(
        self, name: str, user_sub: Optional[str] = None, limit: int = 50
    ) -> List[RegisteredFolder]:
        term = (name or "").strip()
        if not term:
            return []
        query = select(RegisteredFolderModel).where(
            # ilike and not lower(): the column is indexed by nothing here either way, and ilike says what this is.
            RegisteredFolderModel.name.ilike(f"%{_escape_like(term)}%", escape="\\")
        )
        if user_sub is not None:
            query = query.where(RegisteredFolderModel.user_sub == user_sub)
        rows = self._db.execute(
            query.order_by(func.lower(RegisteredFolderModel.name)).limit(max(1, limit))
        ).scalars()
        return [self._to_entity(row) for row in rows]

    def name_taken(self, user_sub: str, name: str, exclude_folder_id: Optional[str] = None) -> bool:
        query = select(RegisteredFolderModel.id).where(
            RegisteredFolderModel.user_sub == user_sub,
            func.lower(RegisteredFolderModel.name) == name.strip().lower(),
        )
        excluded = parse_uuid(exclude_folder_id) if exclude_folder_id else None
        if excluded is not None:
            query = query.where(RegisteredFolderModel.id != excluded)
        return self._db.execute(query.limit(1)).first() is not None

    def folder_names_of_documents(
        self, user_sub: str, document_ids: List[str], exclude_folder_id: Optional[str] = None
    ) -> Dict[str, str]:
        parsed = [i for i in (parse_uuid(i) for i in document_ids) if i is not None]
        if not parsed:
            return {}
        query = (
            select(RegisteredFolderItemModel.document_id, RegisteredFolderModel.name)
            .join(RegisteredFolderModel, RegisteredFolderModel.id == RegisteredFolderItemModel.folder_id)
            .where(
                RegisteredFolderItemModel.document_id.in_(parsed),
                RegisteredFolderModel.user_sub == user_sub,
            )
        )
        excluded = parse_uuid(exclude_folder_id) if exclude_folder_id else None
        if excluded is not None:
            query = query.where(RegisteredFolderItemModel.folder_id != excluded)
        return {str(document_id): name for document_id, name in self._db.execute(query)}

    # ------------------------------------------------------------------ writing

    def create(
        self,
        user_sub: str,
        name: str,
        notes: Optional[str],
        folder_type: str,
        data: Dict[str, Any],
        document_ids: List[str],
    ) -> RegisteredFolder:
        row = RegisteredFolderModel(
            user_sub=user_sub, name=name, notes=notes, folder_type=folder_type, data=data or {}
        )
        row.items = _new_items(document_ids)
        self._db.add(row)
        self._db.commit()
        return self.get(str(row.id), user_sub)

    def update_details(
        self, folder_id: str, name: str, notes: Optional[str], data: Dict[str, Any]
    ) -> None:
        row = self._row(folder_id)
        if row is None:
            return
        row.name = name
        row.notes = notes
        row.data = data or {}
        self._db.commit()

    def file_document(self, folder_id: str, document_id: str) -> None:
        row = self._row(folder_id)
        if row is None:
            return
        if any(str(item.document_id) == document_id for item in row.items):
            return
        row.items.append(
            RegisteredFolderItemModel(
                document_id=parse_uuid(document_id),
                position=max((item.position for item in row.items), default=-1) + 1,
            )
        )
        self._db.commit()

    def set_documents(self, folder_id: str, document_ids: List[str]) -> None:
        row = self._row(folder_id)
        if row is None:
            return
        row.items.clear()
        self._db.flush()
        row.items.extend(_new_items(document_ids))
        self._db.commit()

    def delete(self, folder_id: str) -> None:
        row = self._row(folder_id)
        if row is not None:
            self._db.delete(row)
            self._db.commit()


def _escape_like(term: str) -> str:
    """The term as a literal inside a LIKE pattern."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _new_items(document_ids: List[str]) -> List[RegisteredFolderItemModel]:
    return [
        RegisteredFolderItemModel(document_id=parse_uuid(document_id), position=position)
        for position, document_id in enumerate(document_ids)
    ]
