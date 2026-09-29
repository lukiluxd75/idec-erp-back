from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domains.folder_analysis.domain.entities import DocumentPage, FolderDocument


class DocumentRepositoryPort(ABC):
    @abstractmethod
    def create(self, user_sub: str, doc_type: str, capture_ids: List[str]) -> FolderDocument: ...

    @abstractmethod
    def get(self, document_id: str, user_sub: str) -> Optional[FolderDocument]:
        """Document with its pages and data."""

    @abstractmethod
    def list(self, user_sub: str, doc_type: Optional[str] = None) -> List[FolderDocument]:
        """Newest first, with pages but without extracted/reviewed data."""

    def list_reviewed(self, user_sub: str, doc_type: Optional[str] = None) -> List[FolderDocument]:
        """Newest first, reviewed documents including the data confirmed by the user."""
        return [
            document
            for document in self.list(user_sub, doc_type)
            if document.status == "reviewed"
        ]

    @abstractmethod
    def replace_pages(self, document_id: str, capture_ids: List[str]) -> None:
        """New page list (back to draft, previous results cleared)."""

    @abstractmethod
    def delete(self, document_id: str) -> None: ...

    @abstractmethod
    def mark_submitted(self, document_id: str, job_ids_by_page: Dict[int, str]) -> None:
        """Pages queued with their job ids; document queued; old results cleared."""

    @abstractmethod
    def save_progress(
        self,
        document_id: str,
        pages: List[DocumentPage],
        status: str,
        extracted_data: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> None: ...

    @abstractmethod
    def save_review(self, document_id: str, data: Dict[str, Any]) -> None: ...
