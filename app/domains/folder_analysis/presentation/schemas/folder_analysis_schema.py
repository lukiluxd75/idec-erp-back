from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.domains.folder_analysis.domain.entities import (
    MAX_NAME_LENGTH,
    MAX_NOTES_LENGTH,
    Capture,
    FolderDocument,
    RegisteredFolder,
)
from app.domains.folder_analysis.domain.folder_types import (
    DOCUMENT_TYPES,
    FOLDER_TYPES,
    DocumentTypeSpec,
    FolderTypeSpec,
    document_fields,
    folder_type,
)

# The document type arrives as text and is checked against the catalogue instead
# of a closed Literal: the kinds of document grow with the kinds of carpeta, and
# a list written here would be a second place to keep them in step.
DocType = str


def _known_doc_type(value: Optional[str]) -> Optional[str]:
    if value is not None and value not in DOCUMENT_TYPES:
        raise ValueError("El tipo de documento no es válido.")
    return value


class CaptureOut(BaseModel):
    id: str
    file_name: str
    status: str
    created_at: datetime

    @classmethod
    def from_entity(cls, capture: Capture) -> "CaptureOut":
        return cls(id=capture.id, file_name=capture.file_name, status=capture.status, created_at=capture.created_at)


class ClearedInboxOut(BaseModel):
    """How many photos the bandeja had when it was emptied, so the screen can
    say it instead of leaving the architect guessing whether it did anything."""

    deleted: int


class PhonePresenceOut(BaseModel):
    """Whether a phone of this account is connected right now, for the
    indicator on the web (PhoneConnectedBadge). Same field name the equivalent
    endpoints of geoextraction and resolutions already return, so the frontend
    reads all three the same way."""

    mobile_connected: bool


class PageOut(BaseModel):
    capture_id: str
    page_index: int
    status: str
    error: Optional[str] = None


class DocumentSummary(BaseModel):
    id: str
    doc_type: str
    # The carpeta it was opened in, when it was opened in one, and the kind of
    # carpeta it was classified under (which says what is pulled out of it).
    folder_id: Optional[str] = None
    folder_type: Optional[str] = None
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
            folder_id=document.folder_id,
            folder_type=document.folder_type,
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
    # The carpeta the photos were dropped in. Left out on the loose board.
    folder_id: Optional[str] = None
    # The kind of carpeta being classified, when there is no carpeta open: the
    # loose board picks it in its selector, and it is what decides which values
    # are pulled out of the document. Inside a carpeta, its own kind wins.
    folder_type: Optional[str] = None

    @field_validator("doc_type")
    @classmethod
    def _check_doc_type(cls, value: str) -> str:
        return _known_doc_type(value)


class ConsolidateRequest(BaseModel):
    """Juntar en un documento el carril que la carpeta guarda sin leer.

    No lleva capture_ids: lo que se junta es todo lo que haya en ese carril y
    todo lo que quede en la bandeja, y eso lo sabe el servidor. Mandarlo desde la
    web dejaría fuera lo que llegó del celular mientras la pantalla miraba.
    """

    doc_type: DocType
    folder_id: Optional[str] = None
    folder_type: Optional[str] = None

    @field_validator("doc_type")
    @classmethod
    def _check_doc_type(cls, value: str) -> str:
        return _known_doc_type(value)


class SetPagesRequest(BaseModel):
    capture_ids: List[str] = Field(min_length=1)


class AnalyzeRequest(BaseModel):
    force: bool = False


class ReviewRequest(BaseModel):
    data: Dict[str, Any]


# ---------------------------------------------------------- carpetas registradas


class RegisteredFolderOut(BaseModel):
    """A carpeta with the documents in it, data included: the screen lists a
    carpeta and its documents in one read.

    `folder_type` is the key of its kind and `folder_type_label` the name the
    architect reads, so a list does not have to look the catalogue up for every
    row. `document_types` are the lanes its board shows."""

    id: str
    name: str
    notes: Optional[str] = None
    folder_type: str
    folder_type_label: str
    document_types: List[str]
    data: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentDetail]
    document_count: int
    counts_by_type: Dict[str, int]

    @classmethod
    def from_entity(cls, folder: RegisteredFolder) -> "RegisteredFolderOut":
        spec = folder_type(folder.folder_type)
        return cls(
            id=folder.id,
            name=folder.name,
            notes=folder.notes,
            folder_type=spec.key,
            folder_type_label=spec.label,
            document_types=list(spec.document_types),
            data=folder.data or {},
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            documents=[DocumentDetail.from_entity(d) for d in folder.documents],
            document_count=len(folder.documents),
            counts_by_type=folder.counts_by_type,
        )


class CreateRegisteredFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    notes: Optional[str] = Field(default=None, max_length=MAX_NOTES_LENGTH)
    # The kind of carpeta. Left out, it is the general one -- the three lanes the
    # board had before the catalogue.
    folder_type: Optional[str] = None
    # The carpeta's own sheet; what is not a field of its kind is dropped.
    data: Dict[str, Any] = Field(default_factory=dict)
    document_ids: List[str] = Field(default_factory=list)


class UpdateRegisteredFolderRequest(BaseModel):
    """`document_ids` left out keeps the carpeta's contents as they are; sent, it
    replaces the reviewed documents it holds (an empty list takes all of those
    out). The kind is not here: it is chosen when the carpeta is opened."""

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    notes: Optional[str] = Field(default=None, max_length=MAX_NOTES_LENGTH)
    data: Dict[str, Any] = Field(default_factory=dict)
    document_ids: Optional[List[str]] = None


# -------------------------------------------------------------------- catalogo


class FolderFieldOut(BaseModel):
    """One value on a carpeta's own sheet, as the form has to draw it: `source`
    says where it is copied from ("ide", "document", "fixed", "manual"), and a
    fixed field carries the value it always has."""

    key: str
    label: str
    source: str
    from_document: Optional[str] = None
    value: Optional[str] = None
    hint: Optional[str] = None


class FolderFieldGroupOut(BaseModel):
    key: str
    title: str
    fields: List[FolderFieldOut]


class DocumentValueOut(BaseModel):
    """One value the carpeta pulls out of one of its documents: where it is
    stored and what the review screen calls it."""

    key: str
    label: str
    # Not asked on the review screen; the carpeta sheet still takes it from here.
    hidden: bool = False


class DocumentTypeOut(BaseModel):
    key: str
    label: str
    noun: str
    hint: str
    multi_page: bool

    @classmethod
    def from_spec(cls, spec: DocumentTypeSpec) -> "DocumentTypeOut":
        return cls(
            key=spec.key, label=spec.label, noun=spec.noun, hint=spec.hint, multi_page=spec.multi_page
        )


class FolderTypeOut(BaseModel):
    key: str
    label: str
    description: str
    document_types: List[str]
    field_groups: List[FolderFieldGroupOut]
    # Qué valores se le sacan a cada documento de esta carpeta, por tipo de
    # documento. Un tipo que no está acá se lee genérico (texto y cuadros).
    document_values: Dict[str, List[DocumentValueOut]]

    @classmethod
    def from_spec(cls, spec: FolderTypeSpec) -> "FolderTypeOut":
        return cls(
            key=spec.key,
            label=spec.label,
            description=spec.description,
            document_types=list(spec.document_types),
            document_values={
                doc_type: [
                    DocumentValueOut(key=field.key, label=field.label, hidden=field.hidden)
                    for field in document_fields(spec.key, doc_type)
                ]
                for doc_type in spec.document_types
                if document_fields(spec.key, doc_type)
            },
            field_groups=[
                FolderFieldGroupOut(
                    key=group.key,
                    title=group.title,
                    fields=[
                        FolderFieldOut(
                            key=field.key,
                            label=field.label,
                            source=field.source,
                            from_document=field.from_document,
                            value=field.value,
                            hint=field.hint,
                        )
                        for field in group.fields
                    ],
                )
                for group in spec.field_groups
            ],
        )


class CatalogOut(BaseModel):
    """Everything the screen needs to draw carpetas and lanes without knowing any
    of them by name: which kinds of carpeta exist, which documents each one
    holds and which fields its own sheet asks for."""

    folder_types: List[FolderTypeOut]
    document_types: List[DocumentTypeOut]

    @classmethod
    def current(cls) -> "CatalogOut":
        return cls(
            folder_types=[FolderTypeOut.from_spec(spec) for spec in FOLDER_TYPES.values()],
            document_types=[DocumentTypeOut.from_spec(spec) for spec in DOCUMENT_TYPES.values()],
        )


class AddRegisteredFolderDocumentsRequest(BaseModel):
    document_ids: List[str] = Field(min_length=1)
