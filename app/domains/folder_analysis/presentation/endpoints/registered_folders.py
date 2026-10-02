from typing import List

from fastapi import APIRouter, Depends, status

from app.domains.folder_analysis.application.use_cases import (
    AddDocumentsToRegisteredFolderUseCase,
    CreateRegisteredFolderUseCase,
    DeleteRegisteredFolderUseCase,
    GetRegisteredFolderUseCase,
    ListRegisteredFoldersUseCase,
    RemoveDocumentFromRegisteredFolderUseCase,
    SaveBoardToFolderUseCase,
    UpdateRegisteredFolderUseCase,
)
from app.domains.folder_analysis.presentation.deps import (
    get_add_folder_documents_use_case,
    get_create_registered_folder_use_case,
    get_delete_registered_folder_use_case,
    get_get_registered_folder_use_case,
    get_list_registered_folders_use_case,
    get_remove_folder_document_use_case,
    get_save_board_to_folder_use_case,
    get_update_registered_folder_use_case,
)
from app.domains.folder_analysis.presentation.schemas.folder_analysis_schema import (
    AddRegisteredFolderDocumentsRequest,
    CreateRegisteredFolderRequest,
    RegisteredFolderOut,
    SaveBoardToFolderRequest,
    UpdateRegisteredFolderRequest,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/folders", tags=["Folder analysis · Carpetas registradas"])


@router.get("", response_model=List[RegisteredFolderOut])
def list_folders(
    use_case: ListRegisteredFoldersUseCase = Depends(get_list_registered_folders_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """The user's carpetas A->Z, each with the saved documents filed in it."""
    return [RegisteredFolderOut.from_entity(f) for f in use_case.execute(user.sub)]


@router.post("", response_model=RegisteredFolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(
    body: CreateRegisteredFolderRequest,
    use_case: CreateRegisteredFolderUseCase = Depends(get_create_registered_folder_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """A new carpeta of the kind asked for, with its own sheet and the documents
    already picked for it (if any)."""
    folder = use_case.execute(
        user.sub, body.name, body.notes, body.folder_type, body.data, body.document_ids
    )
    return RegisteredFolderOut.from_entity(folder)


@router.post("/from-board", response_model=RegisteredFolderOut, status_code=status.HTTP_201_CREATED)
def save_board_to_folder(
    body: SaveBoardToFolderRequest,
    use_case: SaveBoardToFolderUseCase = Depends(get_save_board_to_folder_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Saves what was scanned on the loose board into a new carpeta named after
    the physical folder's number."""
    folder = use_case.execute(user.sub, body.folder_number, body.folder_type, body.document_ids)
    return RegisteredFolderOut.from_entity(folder)


@router.get("/{folder_id}", response_model=RegisteredFolderOut)
def get_folder(
    folder_id: str,
    use_case: GetRegisteredFolderUseCase = Depends(get_get_registered_folder_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    return RegisteredFolderOut.from_entity(use_case.execute(folder_id, user.sub))


@router.put("/{folder_id}", response_model=RegisteredFolderOut)
def update_folder(
    folder_id: str,
    body: UpdateRegisteredFolderRequest,
    use_case: UpdateRegisteredFolderUseCase = Depends(get_update_registered_folder_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """The carpeta's name, its note and its own sheet -- and, when `document_ids`
    comes in the body, the reviewed documents it holds, in one save."""
    folder = use_case.execute(
        folder_id, user.sub, body.name, body.notes, body.data, body.document_ids
    )
    return RegisteredFolderOut.from_entity(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id: str,
    use_case: DeleteRegisteredFolderUseCase = Depends(get_delete_registered_folder_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Deletes the carpeta with its documents and their photos."""
    use_case.execute(folder_id, user.sub)


@router.post("/{folder_id}/documents", response_model=RegisteredFolderOut)
def add_documents(
    folder_id: str,
    body: AddRegisteredFolderDocumentsRequest,
    use_case: AddDocumentsToRegisteredFolderUseCase = Depends(get_add_folder_documents_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Files more saved documents at the end of the carpeta."""
    return RegisteredFolderOut.from_entity(use_case.execute(folder_id, user.sub, body.document_ids))


@router.delete("/{folder_id}/documents/{document_id}", response_model=RegisteredFolderOut)
def remove_document(
    folder_id: str,
    document_id: str,
    use_case: RemoveDocumentFromRegisteredFolderUseCase = Depends(
        get_remove_folder_document_use_case
    ),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Takes the document out of the carpeta by deleting it with its photos."""
    return RegisteredFolderOut.from_entity(use_case.execute(folder_id, user.sub, document_id))
