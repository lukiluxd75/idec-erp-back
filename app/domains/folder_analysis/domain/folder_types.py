"""
The catalogue of carpetas: which kinds of carpeta the office works with, which
documents each one holds, and which data the carpeta itself carries.

Until now a lane was a document type and that was the whole story: a folio was
read the same way wherever it came from. A carpeta changes that -- two carpetas
can both hold a folio and need different data out of it -- so what to extract is
keyed by the pair (carpeta, document) and not by the document alone (see
extraction_profiles.profile_for).

Keys are English (internal identifiers, CLAUDE.md §1); the labels are what the
architect reads on screen. This module is data, not behaviour: a new carpeta is a
new entry here, and nothing else in the domain has to learn about it.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# qué carriles tiene una carpeta, y por el paquete eso sería un círculo.
from app.domains.folder_analysis.domain.entities.folder_document import DocumentType


class FieldSource:
    """Where the value of a carpeta's own field comes from.

    A carpeta's sheet is not filled from its photos alone: part of it is copied
    from the IDE (the municipality's spatial data system, which this ERP does not
    talk to yet -- those fields are typed by hand and the screen says where they
    are copied from), part is read off one of its documents, and part is always
    the same word for every carpeta of that kind.
    """

    IDE = "ide"
    DOCUMENT = "document"
    FIXED = "fixed"
    MANUAL = "manual"

    ALL = (IDE, DOCUMENT, FIXED, MANUAL)


@dataclass(frozen=True)
class FolderField:
    """One value on the carpeta's own sheet."""

    key: str
    label: str
    source: str = FieldSource.MANUAL
    # Which document fills it, when the source is a document of this carpeta.
    from_document: Optional[str] = None
    # What it always says, when the source is a fixed value.
    value: Optional[str] = None
    # The line under the field: where to copy it from, or what the office's rule
    # for it is. It is shown to the architect, so it is written in Spanish.
    hint: Optional[str] = None


@dataclass(frozen=True)
class FolderFieldGroup:
    """The fields of a carpeta as they are grouped on paper."""

    key: str
    title: str
    fields: Tuple[FolderField, ...]


@dataclass(frozen=True)
class DocumentTypeSpec:
    """A kind of document a carpeta can hold: one lane of the board."""

    key: str
    label: str
    # How it is named inside a sentence ("se está analizando el plano").
    noun: str
    hint: str
    multi_page: bool = False


@dataclass(frozen=True)
class FolderTypeSpec:
    """A kind of carpeta: its documents and its own sheet."""

    key: str
    label: str
    description: str
    document_types: Tuple[str, ...]
    field_groups: Tuple[FolderFieldGroup, ...] = ()

    @property
    def fields(self) -> Tuple[FolderField, ...]:
        return tuple(field for group in self.field_groups for field in group.fields)

    def holds(self, doc_type: str) -> bool:
        return doc_type in self.document_types


# --- Documents -------------------------------------------------------------
#
# The three that already existed, plus the ones the carpeta de poseedores needs.
# A document with no rules of its own is still read here on the server with the
# generic OCR (its text, its labelled values and its tables) until someone writes
# down what to pull out of it -- see extraction_profiles.

DOCUMENT_TYPES: Dict[str, DocumentTypeSpec] = {
    DocumentType.FOLIO: DocumentTypeSpec(
        key=DocumentType.FOLIO,
        label="Folio",
        noun="el folio",
        hint="Folio Real de Derechos Reales. Puede tener varias páginas.",
        multi_page=True,
    ),
    DocumentType.TAX_RECEIPT: DocumentTypeSpec(
        key=DocumentType.TAX_RECEIPT,
        label="Impuesto",
        noun="el comprobante de impuestos",
        hint="Comprobante de pago del impuesto a la propiedad (FUR).",
    ),
    DocumentType.PLAN: DocumentTypeSpec(
        key=DocumentType.PLAN,
        label="Plano",
        noun="el plano",
        hint="Planos arquitectónicos. Se extrae el texto, los datos y los cuadros con OCR + OpenCV.",
        multi_page=True,
    ),
    DocumentType.APPRAISAL: DocumentTypeSpec(
        key=DocumentType.APPRAISAL,
        label="Avalúo",
        noun="el avalúo",
        hint="Avalúo del inmueble. Puede tener varias páginas.",
        multi_page=True,
    ),
    DocumentType.FORM: DocumentTypeSpec(
        key=DocumentType.FORM,
        label="Formulario",
        noun="el formulario",
        hint="Formulario del trámite. Puede tener varias páginas.",
        multi_page=True,
    ),
    DocumentType.SWORN_STATEMENT: DocumentTypeSpec(
        key=DocumentType.SWORN_STATEMENT,
        label="Declaración jurada",
        noun="la declaración jurada",
        hint="Declaración jurada ante notario. Puede tener varias páginas.",
        multi_page=True,
    ),
    DocumentType.ID_CARD: DocumentTypeSpec(
        key=DocumentType.ID_CARD,
        label="Carnets",
        noun="el carnet",
        hint="Carnets de identidad. Un documento por persona, anverso y reverso.",
        multi_page=True,
    ),
}


# --- Carpetas --------------------------------------------------------------

POSSESSORS = FolderTypeSpec(
    key="possessors",
    label="Poseedores",
    description="Trámite de poseedores: avalúo, plano, formulario, declaración jurada y carnets.",
    document_types=(
        DocumentType.APPRAISAL,
        DocumentType.PLAN,
        DocumentType.FORM,
        DocumentType.SWORN_STATEMENT,
        DocumentType.ID_CARD,
    ),
    field_groups=(
        FolderFieldGroup(
            key="plan",
            title="Datos de plano",
            fields=(
                FolderField(
                    key="street",
                    label="Dirección / calle",
                    source=FieldSource.IDE,
                    hint='Del IDE. Si la calle no tiene nombre, va "calle innominada".',
                ),
                FolderField(
                    key="boundaries",
                    label="Colindancias",
                    source=FieldSource.IDE,
                    hint="Del IDE.",
                ),
                FolderField(key="frontage", label="Frente"),
                FolderField(key="rear_frontage", label="Contra frente"),
                FolderField(key="depth", label="Fondo"),
                FolderField(key="depth_2", label="Fondo 2"),
                FolderField(
                    key="usable_area",
                    label="Superficie útil",
                    hint="Siempre la útil.",
                ),
            ),
        ),
        FolderFieldGroup(
            key="sworn_statement",
            title="Datos de la declaración jurada",
            fields=(
                FolderField(
                    key="notary_number",
                    label="Notario (Nº)",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.SWORN_STATEMENT,
                    hint="Mejor el número del notario que su nombre.",
                ),
                FolderField(
                    key="property_number",
                    label="Número de predio",
                    source=FieldSource.IDE,
                    hint="Del IDE.",
                ),
                FolderField(
                    key="owner_name",
                    label="Nombre del propietario",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.SWORN_STATEMENT,
                    hint="Tal como figura en la declaración jurada.",
                ),
                FolderField(
                    key="statement_dates",
                    label="Fechas de la declaración jurada",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.SWORN_STATEMENT,
                ),
                FolderField(
                    key="legal_status",
                    label="Datos legales",
                    source=FieldSource.FIXED,
                    value="Particular",
                    hint="En poseedores es siempre particular.",
                ),
            ),
        ),
    ),
)


# Every carpeta that existed before this catalogue: the documents already
# analyzed were not filed under any kind of carpeta, and the board showed the
# three original lanes. They keep working under this one.
GENERAL = FolderTypeSpec(
    key="general",
    label="General",
    description="Carpeta sin trámite definido: folio, impuesto y plano, como antes del catálogo.",
    document_types=(DocumentType.FOLIO, DocumentType.TAX_RECEIPT, DocumentType.PLAN),
)


FOLDER_TYPES: Dict[str, FolderTypeSpec] = {
    POSSESSORS.key: POSSESSORS,
    GENERAL.key: GENERAL,
}

# What a carpeta with no kind of its own falls back to, so nothing that already
# exists has to be migrated before it can be opened again.
DEFAULT_FOLDER_TYPE = GENERAL.key


def folder_type(key: Optional[str]) -> FolderTypeSpec:
    """The carpeta's kind, falling back to the general one for the carpetas that
    were created before there were kinds."""
    return FOLDER_TYPES.get(key or DEFAULT_FOLDER_TYPE, GENERAL)


def document_type(key: str) -> Optional[DocumentTypeSpec]:
    return DOCUMENT_TYPES.get(key)


def document_types_of(key: Optional[str]) -> Tuple[str, ...]:
    """The lanes the board shows for a carpeta of this kind."""
    return folder_type(key).document_types


def clean_folder_data(key: Optional[str], data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The carpeta's own sheet, kept to what its kind declares.

    The catalogue is the truth about a carpeta's fields, so a key that is not in
    it is dropped instead of stored (it would never be shown again, and it would
    outlive the field it was typed for). A fixed field always stores the value
    the office's rule gives it, whatever arrived in the request. What is left
    blank is stored as null, so a field emptied on purpose does not keep an old
    value alive.
    """
    spec = folder_type(key)
    incoming = data or {}
    sheet: Dict[str, Any] = {}
    for field in spec.fields:
        if field.source == FieldSource.FIXED:
            sheet[field.key] = field.value
            continue
        value = incoming.get(field.key)
        if isinstance(value, str):
            value = " ".join(value.split()) or None
        sheet[field.key] = value
    return sheet


# --- What to pull out of each document -------------------------------------


@dataclass(frozen=True)
class DocumentField:
    """One value the carpeta needs out of one of its documents.

    `key` is where it is stored (the same key the carpeta's own sheet uses when
    the field feeds it), `label` is what the screen calls it, and `printed` is
    how the label comes written on the sheet -- which is what the reading looks
    for (domain/services/field_harvest.py). Adding a way the label appears is
    adding a string here; nothing else changes.
    """

    key: str
    label: str
    printed: Tuple[str, ...]
    # The office asks for this one by number, not by name (the notary), so only
    # the number of what was read is kept.
    number_only: bool = False


# Keyed by (carpeta, document): the same document read inside two carpetas can
# be asked for different values, which is the whole point of the catalogue.
# A pair with nothing here is read with the generic OCR and stays at its text,
# its labelled values and its cuadros.
DOCUMENT_FIELDS: Dict[Tuple[str, str], Tuple[DocumentField, ...]] = {
    (POSSESSORS_KEY := "possessors", DocumentType.PLAN): (
        DocumentField("frontage", "Frente", ("FRENTE",)),
        DocumentField("rear_frontage", "Contra frente", ("CONTRA FRENTE", "CONTRAFRENTE")),
        DocumentField("depth", "Fondo", ("FONDO",)),
        DocumentField("depth_2", "Fondo 2", ("FONDO 2", "FONDO II", "SEGUNDO FONDO")),
        DocumentField(
            "usable_area",
            "Superficie útil",
            ("SUPERFICIE UTIL", "SUP. UTIL", "SUP UTIL", "AREA UTIL", "SUPERFICIE"),
        ),
    ),
    (POSSESSORS_KEY, DocumentType.SWORN_STATEMENT): (
        DocumentField(
            "notary_number",
            "Notario (Nº)",
            ("NOTARIA DE FE PUBLICA", "NOTARIA", "NOTARIO"),
            number_only=True,
        ),
        DocumentField(
            "owner_name",
            "Nombre del propietario",
            ("NOMBRE DEL PROPIETARIO", "PROPIETARIO", "DECLARANTE"),
        ),
        DocumentField("statement_dates", "Fechas de la declaración jurada", ("FECHA", "FECHAS")),
    ),
}


def document_fields(folder_type_key: Optional[str], doc_type: str) -> Tuple[DocumentField, ...]:
    """What to pull out of a document of this type inside a carpeta of that kind."""
    return DOCUMENT_FIELDS.get((folder_type(folder_type_key).key, doc_type), ())
