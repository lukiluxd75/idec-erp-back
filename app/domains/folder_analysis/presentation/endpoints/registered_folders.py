from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status

from app.domains.folder_analysis.application.use_cases import (
    AddDocumentsToRegisteredFolderUseCase,
    CreateRegisteredFolderUseCase,
    DeleteRegisteredFolderUseCase,
    GetFolderPhotoUseCase,
    GetRegisteredFolderUseCase,
    ListRegisteredFoldersUseCase,
    RemoveDocumentFromRegisteredFolderUseCase,
    SameParcelFoldersUseCase,
    SaveBoardToFolderUseCase,
    SearchRegisteredFoldersUseCase,
    UpdateRegisteredFolderUseCase,
)
from app.domains.folder_analysis.presentation.deps import (
    get_add_folder_documents_use_case,
    get_create_registered_folder_use_case,
    get_delete_registered_folder_use_case,
    get_folder_photo_use_case,
    get_get_registered_folder_use_case,
    get_list_registered_folders_use_case,
    get_remove_folder_document_use_case,
    get_same_parcel_folders_use_case,
    get_save_board_to_folder_use_case,
    get_search_registered_folders_use_case,
    get_update_registered_folder_use_case,
)
from app.domains.folder_analysis.domain.entities import MAX_NAME_LENGTH, CaptureVariant
from app.domains.folder_analysis.presentation.endpoints.captures import cached_image
from app.domains.folder_analysis.presentation.schemas.folder_analysis_schema import (
    AddRegisteredFolderDocumentsRequest,
    CreateRegisteredFolderRequest,
    RegisteredFolderOut,
    SameParcelFolderOut,
    SaveBoardToFolderRequest,
    UpdateRegisteredFolderRequest,
)
from app.domains.security.contracts import (
    UsernameLookup,
    UserProfile,
    get_username_lookup,
    has_permission,
    require_permission,
)

router = APIRouter(prefix="/folders", tags=["Folder analysis · Carpetas registradas"])


@router.get("", response_model=List[RegisteredFolderOut])
def list_folders(
    name: Optional[str] = Query(
        None,
        min_length=2,
        max_length=MAX_NAME_LENGTH,
        description="Búsqueda por nombre de carpeta (el número de la carpeta física).",
    ),
    use_case: ListRegisteredFoldersUseCase = Depends(get_list_registered_folders_use_case),
    search: SearchRegisteredFoldersUseCase = Depends(get_search_registered_folders_use_case),
    owners: UsernameLookup = Depends(get_username_lookup),
    administra: bool = Depends(has_permission("folder-analysis.admin")),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Sin `name`: las carpetas del usuario A->Z, cada una con sus documentos.

    Con `name`: la búsqueda por nombre de carpeta. Quien administra el módulo
    ("folder-analysis.admin") busca entre las carpetas de todos los usuarios y no
    solo entre las suyas -- la carpeta física la escanea quien la tiene en la
    mano, y hasta ahora nadie más podía volver a encontrarla. Quien no lo
    administra busca entre las suyas, que es lo mismo que filtrar su lista.

    Una carpeta ajena solo aparece así, buscándola por su nombre: nunca en la
    lista. Viene marcada (`mine` en falso) con el nombre de su dueño, y es de
    solo lectura -- los endpoints que escriben siguen exigiendo ser su dueño.
    """
    folders = (
        search.execute(user.sub, name, across_users=administra)
        if name
        else use_case.execute(user.sub)
    )
    owner_by_sub = owners(f.user_sub for f in folders if f.user_sub != user.sub)
    return [
        RegisteredFolderOut.from_entity(f, user.sub, owner_by_sub.get(f.user_sub)) for f in folders
    ]


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


@router.get("/{folder_id}/same-parcel", response_model=List[SameParcelFolderOut])
def same_parcel_folders(
    folder_id: str,
    use_case: SameParcelFoldersUseCase = Depends(get_same_parcel_folders_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Las otras carpetas del usuario que son del mismo predio que esta.

    El mismo predio quiere decir el mismo código catastral, que es lo único que
    lo dice: dos carpetas son dos trámites distintos sobre el mismo lote. De cada
    una se contesta lo que tiene escrito de lo que es del predio, para que la
    pantalla lo avise y el arquitecto decida si lo trae. Nada se copia solo.

    Vacío cuando esta carpeta todavía no tiene código catastral, cuando su tipo
    no declara datos del predio, o cuando no hay otra carpeta de ese lote.
    """
    return use_case.execute(folder_id, user.sub)


@router.get("/{folder_id}/photos/{capture_id}")
def get_folder_photo(
    folder_id: str,
    capture_id: str,
    request: Request,
    variant: str = Query(CaptureVariant.PREVIEW, pattern="^(thumbnail|preview|original)$"),
    use_case: GetFolderPhotoUseCase = Depends(get_folder_photo_use_case),
    administra: bool = Depends(has_permission("folder-analysis.admin")),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Una foto escaneada en esta carpeta, para mirarla.

    Es la foto de siempre, pero pedida por la carpeta y no por su dueño: así
    quien administra el módulo puede ver lo que encontró buscando una carpeta
    ajena, y solo eso -- las fotos de esa carpeta, nada de la bandeja de nadie.
    Es de lectura: no hay forma de cambiar nada por acá.

    `variant`: "thumbnail" para una tira de páginas, "preview" para el visor y
    "original" solo cuando se acerca más de lo que el preview aguanta.
    """
    return cached_image(
        request,
        lambda: use_case.execute(folder_id, capture_id, user.sub, administra, variant),
        capture_id,
        variant,
    )


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
