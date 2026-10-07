"""Las carpetas registradas: the architect opens a carpeta, says which kind of
tramite it is, and works its documents inside it.

The kind (domain/folder_types.py) is chosen when the carpeta is opened and does
not change afterwards: the documents already in it were classified under its
lanes, and its sheet was filled with its fields. The sheet itself is kept to what
the kind declares (clean_folder_data).

Deleting a carpeta deletes what was scanned into it as well.

A document opened inside a carpeta is in it from that moment, draft and all. One
already reviewed on the loose board can be filed afterwards from "Datos
guardados" -- that is the only case where being reviewed is required, because
what is being filed is a finished document and not one being worked on. Either
way a document is filed in one carpeta at a time, the way the sheet it came from
sits in a single folder; asking for one that is already somewhere else says where
it is instead of moving it silently.
"""
from typing import Any, Dict, List, Optional, Sequence

from app.domains.folder_analysis.domain.entities import (
    MAX_DOCUMENTS,
    MAX_NAME_LENGTH,
    MAX_NOTES_LENGTH,
    CaptureVariant,
    DocumentStatus,
    RegisteredFolder,
)
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotFoundException,
    DocumentAlreadyFiledException,
    DocumentNotFoundException,
    InvalidDocumentRequestException,
    InvalidRegisteredFolderException,
    RegisteredFolderNameTakenException,
    RegisteredFolderNotFoundException,
)
from app.domains.folder_analysis.domain.folder_types import (
    FOLDER_TYPES,
    PARCEL_CODE_KEY,
    clean_folder_data,
    folder_type,
)
from app.domains.folder_analysis.domain.services import cadastral_code
from app.domains.folder_analysis.application.use_cases.capture_use_cases import (
    GetCaptureImageUseCase,
    forget_previews,
)
from app.domains.folder_analysis.domain.ports import (
    CaptureRepositoryPort,
    DocumentRepositoryPort,
    RegisteredFolderRepositoryPort,
)


# Lo mínimo que hay que escribir para que una búsqueda sea una búsqueda.
MIN_SEARCH_LENGTH = 2


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


def _clean_folder_type(key: Optional[str]) -> str:
    """The kind of carpeta, which has to be one the catalogue knows: an unknown
    one would come back from the database with lanes and fields nobody declared."""
    chosen = (key or "").strip() or None
    if chosen is None:
        return folder_type(None).key
    if chosen not in FOLDER_TYPES:
        raise InvalidRegisteredFolderException("Ese tipo de carpeta no existe.")
    return chosen


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
        self,
        user_sub: str,
        name: str,
        exclude_folder_id: Optional[str] = None,
        taken_message: Optional[str] = None,
    ) -> None:
        if self._folders.name_taken(user_sub, name, exclude_folder_id):
            raise RegisteredFolderNameTakenException(
                taken_message or f'Ya tiene una carpeta llamada "{name}". Use otro nombre.'
            )

    def require_filable(
        self,
        user_sub: str,
        document_ids: List[str],
        exclude_folder_id: Optional[str] = None,
        reviewed_only: bool = True,
    ) -> None:
        """`reviewed_only` is off only when the loose board is saved whole into a
        new carpeta: what goes in then is the work in progress of one physical
        folder, not a finished document filed on its own."""
        if not document_ids:
            return
        # One listing instead of a query per document: this is the summary list, so it carries no extracted/reviewed JSON.
        status_by_id: Dict[str, str] = {
            document.id: document.status for document in self._documents.list(user_sub)
        }
        if any(document_id not in status_by_id for document_id in document_ids):
            raise DocumentNotFoundException(
                "Uno de los documentos seleccionados no existe o no le pertenece."
            )
        if reviewed_only and any(
            status_by_id[document_id] != DocumentStatus.REVIEWED for document_id in document_ids
        ):
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


class SearchRegisteredFoldersUseCase:
    """Encontrar una carpeta por su nombre, que es el número de la carpeta física.

    Para quien solo usa el módulo busca entre las suyas, que es lo mismo que
    filtrar su lista. Para quien lo administra busca entre las de todos los
    usuarios: una carpeta la escanea quien la tiene en la mano, y hasta ahora el
    resto no tenía forma de volver a encontrarla -- había que adivinar de quién
    era. Solo por nombre y solo buscando: las carpetas ajenas no aparecen en la
    lista de nadie, y escribir en una sigue siendo cosa de su dueño
    (RegisteredFolderService.require_folder no cambió).

    Un término demasiado corto no busca nada: con una letra, "buscar entre las de
    todos" devuelve media base y ninguna de esas filas es una respuesta.
    """

    def __init__(self, folders: RegisteredFolderRepositoryPort):
        self._folders = folders

    def execute(
        self, user_sub: str, name: str, across_users: bool = False
    ) -> List[RegisteredFolder]:
        term = " ".join((name or "").split())
        if len(term) < MIN_SEARCH_LENGTH:
            return []
        return self._folders.search_by_name(term, None if across_users else user_sub)


class GetFolderPhotoUseCase:
    """Una foto de una carpeta, para mirarla.

    El dueño llega acá igual que por la bandeja. Quien administra el módulo
    llega también, pero solo hasta las fotos que son páginas de un documento
    archivado en esa carpeta: no a una foto suelta de otro usuario, ni a un
    documento que no esté en la carpeta, ni a la carpeta de alguien si no la
    encontró antes. Es exactamente lo que ya ve en pantalla cuando la busca por
    su nombre, y sigue sin poder tocar nada.

    La imagen se lee a nombre del dueño de la carpeta, no de quien pregunta: la
    foto es suya y el permiso ya se resolvió una línea más arriba.

    Una carpeta que no existe y una a la que no se llega contestan lo mismo, para
    no convertir esto en una forma de averiguar qué carpetas hay.
    """

    def __init__(
        self,
        folders: RegisteredFolderRepositoryPort,
        images: GetCaptureImageUseCase,
    ):
        self._folders = folders
        self._images = images

    def execute(
        self,
        folder_id: str,
        capture_id: str,
        user_sub: str,
        administra: bool = False,
        variant: str = CaptureVariant.PREVIEW,
    ):
        folder = self._folders.find_any(folder_id)
        if folder is None or (folder.user_sub != user_sub and not administra):
            raise RegisteredFolderNotFoundException()
        pages = (page for document in folder.documents for page in document.pages)
        if not any(page.capture_id == capture_id for page in pages):
            raise CaptureNotFoundException("Esa foto no es de esta carpeta.")
        return self._images.execute(capture_id, folder.user_sub, variant)


class GetRegisteredFolderUseCase:
    def __init__(self, service: RegisteredFolderService):
        self._service = service

    def execute(self, folder_id: str, user_sub: str) -> RegisteredFolder:
        return self._service.require_folder(folder_id, user_sub)


# Cuántas carpetas del mismo predio se contestan. Son los trámites anteriores
# del mismo lote: con más de un puñado, lo que hay que mirar es el predio y no
# una lista.
MAX_SAME_PARCEL = 5


class SameParcelFoldersUseCase:
    """Las otras carpetas del usuario que son del mismo predio que esta.

    Dos carpetas son del mismo predio cuando su código catastral es el mismo
    -- el del GIS, que es el que no cambia aunque una hoja lo imprima con el par
    de adelante y la otra sin él (cadastral_code.to_gis_code). Y eso es lo único
    que las hace comparables: son dos trámites distintos, de dos momentos
    distintos, sobre el mismo lote. Sin el código, dos carpetas no tienen nada
    que decirse -- traerle un dato de otra sería meter el número de otro predio
    sin que nada lo garantice.

    De esas carpetas se contesta solo lo que es del PREDIO (el apartado que el
    catálogo marca así, FolderFieldGroup.about_the_parcel): la superficie, las
    medidas, la calle y las colindancias son del lote y no cambian de un trámite
    al otro. El notario, los poseedores y la fecha de la declaración son de este
    trámite y de su gente, así que no se ofrecen aunque el lote sea el mismo.

    No llena nada: contesta para que la pantalla lo avise y el arquitecto
    decida. Una carpeta vieja puede tener un dato mal cargado, y el trámite que
    se está haciendo ahora es el que manda.

    Solo entre carpetas del mismo tipo y del mismo dueño: las claves de la hoja
    significan lo que dice el catálogo de ese tipo, y una carpeta ajena no
    aparece en la lista de nadie (ver SearchRegisteredFoldersUseCase).
    """

    def __init__(
        self, folders: RegisteredFolderRepositoryPort, service: RegisteredFolderService
    ):
        self._folders = folders
        self._service = service

    def execute(self, folder_id: str, user_sub: str) -> List[Dict[str, Any]]:
        folder = self._service.require_folder(folder_id, user_sub)
        kind = folder_type(folder.folder_type)
        fields = kind.parcel_fields
        code = self._code_of(folder)
        if not fields or code is None:
            return []
        found: List[Dict[str, Any]] = []
        for other in self._folders.list_sheets(user_sub):
            if other.id == folder.id or folder_type(other.folder_type).key != kind.key:
                continue
            if _gis_code(other.data.get(PARCEL_CODE_KEY)) != code:
                continue
            values = [
                {"key": field.key, "label": field.label, "value": value}
                for field in fields
                for value in [_written(other.data.get(field.key))]
                if value is not None
            ]
            if not values:
                # La misma carpeta del predio sin nada escrito todavía: nombrarla no ayuda a nadie.
                continue
            found.append(
                {
                    "id": other.id,
                    "name": other.name,
                    "folder_type": folder_type(other.folder_type).key,
                    "printed_code": cadastral_code.printed(code),
                    "updated_at": other.updated_at,
                    "values": values,
                }
            )
            if len(found) == MAX_SAME_PARCEL:
                break
        return found

    @staticmethod
    def _code_of(folder: RegisteredFolder) -> Optional[str]:
        """El código catastral de la carpeta: el de su hoja y, si ahí no está
        todavía, el que le leyeron a sus documentos.

        La hoja se llena sola con el código del plano en cuanto se lo lee, así
        que casi siempre está ahí; los documentos quedan para la carpeta recién
        leída, cuya hoja todavía no se guardó.
        """
        code = _gis_code(folder.data.get(PARCEL_CODE_KEY))
        if code is not None:
            return code
        for document in folder.documents:
            values = (document.current_data or {}).get("values") or {}
            code = _gis_code(values.get(PARCEL_CODE_KEY))
            if code is not None:
                return code
        return None


def _gis_code(value: Any) -> Optional[str]:
    """El código como lo conoce el GIS, o None cuando lo escrito no es un código.

    Un código a medio escribir no es un error que haya que contar: es una
    carpeta que todavía no dice de qué predio es.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return cadastral_code.to_gis_code(value)
    except InvalidDocumentRequestException:
        return None


def _written(value: Any) -> Optional[str]:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    return " ".join(str(value).split()) or None


class CreateRegisteredFolderUseCase:
    """A new carpeta of a given kind, with whatever of its sheet is already known
    and, optionally, documents already reviewed that are being filed into it."""

    def __init__(self, folders: RegisteredFolderRepositoryPort, service: RegisteredFolderService):
        self._folders = folders
        self._service = service

    def execute(
        self,
        user_sub: str,
        name: str,
        notes: Optional[str] = None,
        folder_type_key: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> RegisteredFolder:
        clean_name = _clean_name(name)
        clean_notes = _clean_notes(notes)
        kind = _clean_folder_type(folder_type_key)
        ids = _unique_ids(document_ids)
        self._service.require_free_name(user_sub, clean_name)
        self._service.require_filable(user_sub, ids)
        return self._folders.create(
            user_sub, clean_name, clean_notes, kind, clean_folder_data(kind, data), ids
        )


class SaveBoardToFolderUseCase:
    """"Guardar en carpeta" from the loose board.

    A whole physical folder is scanned on the loose board; when it is done, the
    architect types the folder's number and everything on the board goes into a
    new carpeta named after that number, whatever state each document is in
    (still being read, read, or reviewed). The carpeta takes the kind the board
    was showing, and the documents must be of that kind's lanes and not filed
    anywhere else yet.
    """

    def __init__(
        self,
        folders: RegisteredFolderRepositoryPort,
        documents: DocumentRepositoryPort,
        service: RegisteredFolderService,
    ):
        self._folders = folders
        self._documents = documents
        self._service = service

    def execute(
        self,
        user_sub: str,
        folder_number: str,
        folder_type_key: Optional[str],
        document_ids: Sequence[str],
    ) -> RegisteredFolder:
        number = _clean_name(folder_number)
        kind = _clean_folder_type(folder_type_key)
        ids = _unique_ids(document_ids)
        if not ids:
            raise InvalidRegisteredFolderException(
                "No hay documentos en el tablero para guardar en la carpeta."
            )
        self._service.require_free_name(
            user_sub,
            number,
            taken_message=f'Ya existe una carpeta registrada con el número "{number}". Verifique el número.',
        )
        self._service.require_filable(user_sub, ids, reviewed_only=False)
        lanes = folder_type(kind).document_types
        doc_type_by_id = {document.id: document.doc_type for document in self._documents.list(user_sub)}
        if any(doc_type_by_id.get(document_id) not in lanes for document_id in ids):
            raise InvalidRegisteredFolderException(
                "Hay documentos que no corresponden a este tipo de carpeta."
            )
        return self._folders.create(user_sub, number, None, kind, clean_folder_data(kind, None), ids)


class UpdateRegisteredFolderUseCase:
    """The carpeta's name, its note and its sheet -- and, when `document_ids` is
    given, which reviewed documents it holds. Leaving `document_ids` out keeps
    the contents untouched, so renaming never risks the selection.

    What arrives replaces only the reviewed documents. The screen that sends it
    lists those and nothing else, so a document still being worked on inside the
    carpeta is not in that selection and must not be thrown out of the carpeta by
    a rename.

    The kind is not here: it was chosen when the carpeta was opened, and the
    documents inside it were classified under its lanes.
    """

    def __init__(self, folders: RegisteredFolderRepositoryPort, service: RegisteredFolderService):
        self._folders = folders
        self._service = service

    def execute(
        self,
        folder_id: str,
        user_sub: str,
        name: str,
        notes: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> RegisteredFolder:
        folder = self._service.require_folder(folder_id, user_sub)
        clean_name = _clean_name(name)
        clean_notes = _clean_notes(notes)
        self._service.require_free_name(user_sub, clean_name, exclude_folder_id=folder_id)
        if document_ids is not None:
            chosen = _unique_ids(document_ids)
            unfinished = [
                document.id
                for document in folder.documents
                if document.status != DocumentStatus.REVIEWED and document.id not in chosen
            ]
            added = [i for i in chosen if i not in folder.document_ids]
            self._service.require_filable(user_sub, added, exclude_folder_id=folder_id)
            self._folders.set_documents(folder_id, _unique_ids([*chosen, *unfinished]))
        self._folders.update_details(
            folder_id, clean_name, clean_notes, clean_folder_data(folder.folder_type, data)
        )
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
    """Takes one document out of the carpeta by deleting it with its photos.
    Sending it back to the loose board would mix it with the next physical
    folder being scanned there."""

    def __init__(
        self,
        folders: RegisteredFolderRepositoryPort,
        service: RegisteredFolderService,
        documents: DocumentRepositoryPort,
        captures: CaptureRepositoryPort,
    ):
        self._folders = folders
        self._service = service
        self._documents = documents
        self._captures = captures

    def execute(self, folder_id: str, user_sub: str, document_id: str) -> RegisteredFolder:
        folder = self._service.require_folder(folder_id, user_sub)
        document = next((d for d in folder.documents if d.id == document_id), None)
        if document is None:
            raise DocumentNotFoundException("Ese documento no está en esta carpeta.")
        capture_ids = [page.capture_id for page in document.pages]
        self._folders.set_documents(
            folder_id, [i for i in folder.document_ids if i != document_id]
        )
        # Document before photos: its pages hold the photos' ids.
        self._documents.delete(document_id)
        self._captures.delete_many(capture_ids, user_sub)
        forget_previews(capture_ids)
        return self._service.require_folder(folder_id, user_sub)


class DeleteRegisteredFolderUseCase:
    """Removes the carpeta together with everything scanned into it: its
    documents and their photos. Putting them back on the loose board would mix
    them with the next physical folder being scanned there."""

    def __init__(
        self,
        folders: RegisteredFolderRepositoryPort,
        service: RegisteredFolderService,
        documents: DocumentRepositoryPort,
        captures: CaptureRepositoryPort,
    ):
        self._folders = folders
        self._service = service
        self._documents = documents
        self._captures = captures

    def execute(self, folder_id: str, user_sub: str) -> None:
        folder = self._service.require_folder(folder_id, user_sub)
        capture_ids = [page.capture_id for document in folder.documents for page in document.pages]
        self._folders.delete(folder_id)
        # Documents before photos: their pages hold the photos' ids.
        for document in folder.documents:
            self._documents.delete(document.id)
        self._captures.delete_many(capture_ids, user_sub)
        forget_previews(capture_ids)
