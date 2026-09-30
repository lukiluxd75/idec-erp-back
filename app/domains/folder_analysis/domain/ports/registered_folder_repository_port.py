from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domains.folder_analysis.domain.entities import RegisteredFolder


class RegisteredFolderRepositoryPort(ABC):
    """Storage of the project folders ("carpetas registradas") and of which
    reviewed documents each one holds."""

    @abstractmethod
    def create(
        self,
        user_sub: str,
        name: str,
        notes: Optional[str],
        folder_type: str,
        data: Dict[str, Any],
        document_ids: List[str],
    ) -> RegisteredFolder: ...

    @abstractmethod
    def get(self, folder_id: str, user_sub: str) -> Optional[RegisteredFolder]:
        """The carpeta with its documents, data included, in filing order."""

    @abstractmethod
    def list(self, user_sub: str) -> List[RegisteredFolder]:
        """The user's carpetas A->Z by name, each with its documents."""

    @abstractmethod
    def update_details(
        self, folder_id: str, name: str, notes: Optional[str], data: Dict[str, Any]
    ) -> None:
        """The carpeta's name, its note and its own sheet. Its kind is not here:
        it is chosen when the carpeta is opened and does not change afterwards,
        because the documents already inside it were classified under it."""

    @abstractmethod
    def file_document(self, folder_id: str, document_id: str) -> None:
        """Files one document at the end of the carpeta. This is how a document
        opened inside a carpeta joins it, before it has been analyzed."""

    @abstractmethod
    def set_documents(self, folder_id: str, document_ids: List[str]) -> None:
        """The carpeta's whole content, in the given order (adds and removes)."""

    @abstractmethod
    def delete(self, folder_id: str) -> None:
        """Only the carpeta: the documents it held stay in "Datos guardados"."""

    @abstractmethod
    def name_taken(self, user_sub: str, name: str, exclude_folder_id: Optional[str] = None) -> bool:
        """Another carpeta of this user already goes by that name (case-insensitive)."""

    @abstractmethod
    def folder_names_of_documents(
        self, user_sub: str, document_ids: List[str], exclude_folder_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Of the documents asked for, the ones already filed somewhere else:
        document id -> name of the carpeta holding it."""
