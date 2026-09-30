"""The "Carpetas registradas" screen, inside "Datos guardados": the architect
groups the documents already solved -- folios, comprobantes de impuestos and
planos -- under a name they choose, so a project's papers stay together.

Only a document whose review was saved can be filed: while it is still being
read or corrected there is nothing final to file. And a document is filed in one
carpeta at a time, the way the sheet it came from sits in a single folder; asking
for one that is already somewhere else says where it is instead of moving it
silently.
"""
from typing import Dict, List, Optional, Sequence

from app.domains.folder_analysis.domain.entities import (
    MAX_DOCUMENTS,
    MAX_NAME_LENGTH,
    MAX_NOTES_LENGTH,
    DocumentStatus,
    RegisteredFolder,
)
from app.domains.folder_analysis.domain.exceptions import (
    DocumentAlreadyFiledException,
    DocumentNotFoundException,
    InvalidRegisteredFolderException,
    RegisteredFolderNameTakenException,
    RegisteredFolderNotFoundException,
)
from app.domains.folder_analysis.domain.ports import (
    DocumentRepositoryPort,
    RegisteredFolderRepositoryPort,
)


def _clean_name(name: Optional[str]) -> str:
    """The name is how the architect finds the project again, so it is required
    and kept as typed (only trimmed)."""
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise InvalidRegisteredFolderException("Escriba un nombre para la carpeta.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise InvalidRegisteredFolderException(
            f"El nombre de la carpeta no puede pasar de {MAX_NAME_LENGTH} caracteres."
        )
    return cleaned


def _clean_notes(notes: Optional[str]) -> Optional[str]:
    cleaned = (notes or "").strip()
    if len(cleaned) > MAX_NOTES_LENGTH:
        raise InvalidRegisteredFolderException(
            f"La descripción no puede pasar de {MAX_NOTES_LENGTH} caracteres."
        )
    return cleaned or None


def _unique_ids(document_ids: Optional[Sequence[str]]) -> List[str]:
    """Keeps the order the architect picked them in, without repeats."""
    ids = list(dict.fromkeys(document_ids or []))
    if len(ids) > MAX_DOCUMENTS:
        raise InvalidRegisteredFolderException(
            f"Una carpeta admite como máximo {MAX_DOCUMENTS} documentos."
        )
    return ids


class RegisteredFolderService:
    """The checks every write shares: the name is free, and every document asked
    for is the user's, reviewed, and not already filed elsewhere."""

    def __init__(self, folders: RegisteredFolderRepositoryPort, documents: DocumentRepositoryPort):
        self._folders = folders
        self._documents = documents

    def require_folder(self, folder_id: str, user_sub: str) -> RegisteredFolder:
        folder = self._folders.get(folder_id, user_sub)
        if folder is None:
            raise RegisteredFolderNotFoundException()
        return folder

    def require_free_name(
        self, user_sub: str, name: str, exclude_folder_id: Optional[str] = None
    ) -> None:
        if self._folders.name_taken(user_sub, name, exclude_folder_id):
            raise RegisteredFolderNameTakenException(
                f'Ya tiene una carpeta llamada "{name}". Use otro nombre.'
            )

    def require_filable(
        self, user_sub: str, document_ids: List[str], exclude_folder_id: Optional[str] = None
    ) -> None:
        if not document_ids:
            return
        # One listing instead of a query per document: this is the summary list,
        # so it carries no extracted/reviewed JSON.
        status_by_id: Dict[str, str] = {
            document.id: document.status for document in self._documents.list(user_sub)
        }
        if any(document_id not in status_by_id for document_id in document_ids):
            raise DocumentNotFoundException(
                "Uno de los documentos seleccionados no existe o no le pertenece."
            )
        if any(status_by_id[document_id] != DocumentStatus.REVIEWED for document_id in document_ids):
            raise InvalidRegisteredFolderException(
                "Solo puede guardar en una carpeta los documentos cuya revisión ya fue guardada."
            )
        elsewhere = self._folders.folder_names_of_documents(
            user_sub, document_ids, exclude_folder_id
        )
        if elsewhere:
            names = ", ".join(sorted(set(elsewhere.values())))
            raise DocumentAlreadyFiledException(
                f"Hay documentos de esta selección en otra carpeta ({names}). "
                "Quítelos de ahí antes de guardarlos aquí."
            )


class ListRegisteredFoldersUseCase:
    """The carpetas A->Z, each with the saved data of the documents it holds."""

    def __init__(self, folders: RegisteredFolderRepositoryPort):
        self._folders = folders

    def execute(self, user_sub: str) -> List[RegisteredFolder]:
        return self._folders.list(user_sub)


class GetRegisteredFolderUseCase:
    def __init__(self, service: RegisteredFolderService):
        self._service = service

    def execute(self, folder_id: str, user_sub: str) -> RegisteredFolder:
        return self._service.require_folder(folder_id, user_sub)


class CreateRegisteredFolderUseCase:
    """A new project folder, optionally already holding the documents picked on
    the same screen."""

    def __init__(self, folders: RegisteredFolderRepositoryPort, service: RegisteredFolderService):
        self._folders = folders
        self._service = service

    def execute(
        self,
        user_sub: str,
        name: str,
        notes: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> RegisteredFolder:
        clean_name = _clean_name(name)
        clean_notes = _clean_notes(notes)
        ids = _unique_ids(document_ids)
        self._service.require_free_name(user_sub, clean_name)
        self._service.require_filable(user_sub, ids)
        return self._folders.create(user_sub, clean_name, clean_notes, ids)


class UpdateRegisteredFolderUseCase:
    """Renames the carpeta and, when `document_ids` is given, replaces what it
    holds -- adding, removing and reordering in one save. Leaving it out keeps
    the contents untouched, so renaming never risks the selection."""

    def __init__(self, folders: RegisteredFolderRepositoryPort, service: RegisteredFolderService):
        self._folders = folders
        self._service = service

    def execute(
        self,
        folder_id: str,
        user_sub: str,
        name: str,
        notes: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> RegisteredFolder:
        self._service.require_folder(folder_id, user_sub)
        clean_name = _clean_name(name)
        clean_notes = _clean_notes(notes)
        self._service.require_free_name(user_sub, clean_name, exclude_folder_id=folder_id)
        if document_ids is not None:
            ids = _unique_ids(document_ids)
            self._service.require_filable(user_sub, ids, exclude_folder_id=folder_id)
            self._folders.set_documents(folder_id, ids)
        self._folders.rename(folder_id, clean_name, clean_notes)
        return self._service.require_folder(folder_id, user_sub)


class AddDocumentsToRegisteredFolderUseCase:
    """Files more documents at the end of the carpeta, keeping what is in it."""

    def __init__(self, folders: RegisteredFolderRepositoryPort, service: RegisteredFolderService):
        self._folders = folders
        self._service = service

    def execute(
        self, folder_id: str, user_sub: str, document_ids: Sequence[str]
    ) -> RegisteredFolder:
        folder = self._service.require_folder(folder_id, user_sub)
        current = folder.document_ids
        added = [i for i in dict.fromkeys(document_ids or []) if i not in current]
        if not added:
            raise InvalidRegisteredFolderException("Seleccione al menos un documento para agregar.")
        ids = _unique_ids([*current, *added])
        self._service.require_filable(user_sub, added, exclude_folder_id=folder_id)
        self._folders.set_documents(folder_id, ids)
        return self._service.require_folder(folder_id, user_sub)


class RemoveDocumentFromRegisteredFolderUseCase:
    """Takes one document out of the carpeta. The document itself is untouched:
    it stays in "Datos guardados", free to file in another carpeta."""

    def __init__(self, folders: RegisteredFolderRepositoryPort, service: RegisteredFolderService):
        self._folders = folders
        self._service = service

    def execute(self, folder_id: str, user_sub: str, document_id: str) -> RegisteredFolder:
        folder = self._service.require_folder(folder_id, user_sub)
        if document_id not in folder.document_ids:
            raise DocumentNotFoundException("Ese documento no está en esta carpeta.")
        self._folders.set_documents(
            folder_id, [i for i in folder.document_ids if i != document_id]
        )
        return self._service.require_folder(folder_id, user_sub)


class DeleteRegisteredFolderUseCase:
    """Removes the carpeta only. Its documents go back to being unfiled."""

    def __init__(self, folders: RegisteredFolderRepositoryPort, service: RegisteredFolderService):
        self._folders = folders
        self._service = service

    def execute(self, folder_id: str, user_sub: str) -> None:
        self._service.require_folder(folder_id, user_sub)
        self._folders.delete(folder_id)
