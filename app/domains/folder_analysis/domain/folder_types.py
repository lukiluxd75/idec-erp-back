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
from app.domains.folder_analysis.domain.services import spanish_dates


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
        label="Otros documentos",
        noun="el documento",
        hint="Respaldos que acompañan a la carpeta: carnets y cualquier otra hoja. Se guardan con sus fotos, no se leen.",
        multi_page=True,
    ),
}


# --- Carpetas --------------------------------------------------------------

POSSESSORS = FolderTypeSpec(
    key="possessors",
    label="Registro catastral de poseedores",
    description="Trámite de poseedores: avalúo, plano, formulario, declaración jurada y otros documentos.",
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
                    key="cadastral_code",
                    label="Código catastral",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.PLAN,
                    hint="Lo impreso en el plano; con él se ubica el predio en el IDE.",
                ),
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
                    hint=(
                        "Se guarda el número, no el nombre. Sale del sello del documento y, "
                        "cuando el sello no se puede leer, del texto."
                    ),
                ),
                FolderField(
                    key="property_number",
                    label="Número de predio",
                    source=FieldSource.IDE,
                    hint="Del IDE.",
                ),
                FolderField(
                    key="owner_name",
                    label="Nombres de los poseedores",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.SWORN_STATEMENT,
                    hint="Todos los que firman, separados por coma, tal como figuran en la declaración jurada.",
                ),
                FolderField(
                    key="statement_dates",
                    label="Fecha de la declaración jurada",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.SWORN_STATEMENT,
                    hint="En dd/mm/aaaa. El acta la escribe con letras y la lectura la pasa a cifras.",
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
    printed: Tuple[str, ...] = ()
    # The office asks for this one by number, not by name (the notary), so only
    # the number of what was read is kept.
    number_only: bool = False
    # How the value is written when the sheet has no labels at all -- a notarial
    # act is running prose, and what identifies a value there is the sentence it
    # sits in ("se hizo presente NOMBRE con Cédula de Identidad"). Regexes over
    # the normalized text (uppercase, no accents, single spaces); group 1 is the
    # value, or the named groups the transform asks for.
    patterns: Tuple[str, ...] = ()
    # Cómo viene escrito el valor DENTRO del sello, para un campo que vive en la
    # estampa redonda y no en la redacción. El sello no se lee con el texto de la
    # hoja: se lo busca en la imagen, se lo recorta y se desenrolla su corona
    # (infrastructure/opencv_seal_reader.py), y por eso sus patrones son otros --
    # dentro del recorte ya se sabe de qué sello se trata, así que no hay que
    # volver a reconocerlo, solo encontrar el valor. Un campo que declara esto se
    # llena con lo que diga el sello antes que con lo que diga el texto.
    seal_patterns: Tuple[str, ...] = ()
    # Post-processing of what the pattern matched. Today only "spanish_date",
    # which turns a date written in words into dd/mm/aaaa.
    transform: Optional[str] = None
    # The value comes from the IDE lookup on the review screen, not from the text
    # of the sheet: the reading has nothing to search for and its absence is not
    # a missing label.
    from_ide: bool = False
    # Filled on the review screen but not shown in the block of values: the carpeta
    # sheet still takes it from here, the plano just has nothing to confirm in it.
    hidden: bool = False
    # Every match of every pattern, not just the first: a plano prints the width of
    # each street it faces.
    collect_all: bool = False


# Cómo viene escrita la cédula detrás de un nombre. Es lo que marca dónde termina
# el nombre, así que tiene que aguantar lo que el OCR hace con dos letras sueltas:
# la I sale L o 1 ("CON C.L:5932821" por "con C.I: 5932821"), y los puntos y el
# espacio aparecen o no según cómo salió la foto.
_ID_CARD = r"(?:CEDULA DE IDENTIDAD|C\.?\s?[IL1]\.?)"


# Lo que se le saca a un acta notarial. No tiene rótulos: el número del notario,
# la persona y la fecha están dentro de su redacción, así que cada campo dice en
# qué frase vive. Las etiquetas (`printed`) quedan igual para la hoja que sí las
# trae rotuladas, como un formulario municipal con casillas.
NOTARIAL_FIELDS: Tuple["DocumentField", ...] = (
    DocumentField(
        "notary_number",
        "Notario (Nº)",
        printed=("NOTARIA DE FE PUBLICA", "NOTARIA", "NOTARIO"),
        number_only=True,
        patterns=(
            # "Notario de Fe Pública N° 15", y sobre todo el sello, que es de
            # donde sale el número cuando la minuta no lo escribe: redondo,
            # girado y con el oficio en medio, el OCR lo devuelve hecho pedazos
            # ("NOTARIA DEFE PULCA DEP.SMERA CLAN0.48", "NOTARIADEFE PURUCA
            # DEPAIMERA CLASENo.48"). Por eso solo se exige "NOTARI(A|O) DE FE"
            # --que sobrevive aun pegado-- y después, dentro de unos pocos
            # caracteres de letras, el número con su marca.
            #
            # "PUBLICA" no se exige: sale "PULCA" o "PURUCA" casi siempre. La
            # marca admite el cero que el OCR pone por O ("N0.48"); normalizado,
            # "Nº" queda "NO" y "Nro." queda "NRO.".
            #
            # La marca no lleva límite de palabra delante a propósito: el sello
            # sale con "CLASE No." pegado ("CLAN0.48", "CLASENO.48"), así que la
            # N queda dentro de una palabra. Lo que sostiene el patrón es que
            # detrás venga el número.
            #
            # Pedir "DE FE" es lo que distingue al notario de esta hoja del que
            # reconoció el documento anterior ("ante Notario de Primera Clase
            # Nro. 44"), que no lleva esas palabras.
            r"NOTARI[AO]\s*DE\s*FE[A-Z\s,.-]{0,40}?(?:NRO|N[O0°])\.?\s*(\d{1,3})\b",
        ),
        # Y el sello mismo, que es de donde sale el número siempre: una minuta va
        # dirigida al notario y no lo nombra, y el notario que sí nombra es el
        # que reconoció el documento anterior. El sello se busca en la foto y se
        # lee aparte, así que acá llega el texto de UN sello y nada más.
        #
        # Por eso no se exige "NOTARI(A|O) DE FE" delante: dentro del recorte ya
        # se sabe que es el sello del notario, y exigirlo es justamente lo que
        # falla cuando el desenrollado de la corona parte la leyenda en dos. Lo
        # que sostiene el patrón es la marca de número con su número: en un sello
        # no hay otra cifra de tres dígitos que pueda confundirse con esa (un
        # teléfono y un año tienen más, y el patrón pide que el número termine
        # ahí).
        seal_patterns=(
            # "NOTARIA DE FE PUBLICA No. 48", "CLAN0.48" del sello partido.
            r"(?:NRO|N[O0°])\.?\s*(\d{1,3})\b",
            # El sello al que el OCR le comió la marca: "DE PRIMERA CLASE 48".
            r"CLASE\s*(\d{1,3})\b",
        ),
    ),
    DocumentField(
        "owner_name",
        "Nombres de los poseedores",
        printed=("NOMBRE DEL PROPIETARIO", "PROPIETARIO", "DECLARANTE"),
        # Todos los que firman, no el primero: una carpeta de poseedores casi
        # siempre va a nombre de dos (los cónyuges), y quedarse con uno obligaba
        # a copiar el otro a mano sin que nada avisara que faltaba. Van separados
        # por coma, en el orden en que la hoja los enumera.
        collect_all=True,
        patterns=(
            # "se hizo presente NOELIA ALMENDRAS RODRIGUEZ con Cédula de Identidad"
            rf"SE HIZO PRESENTE[,:\s]+(.+?)[,\s]+CON {_ID_CARD}",
            rf"(?:COMPARECE|COMPARECIO)[,:\s]+(.+?)[,\s]+CON {_ID_CARD}",
            # Una minuta dirigida al notario no dice "compareció": enumera a las
            # partes y cuelga la cédula de cada nombre ("1.- JUAN CHILE ARIAS.
            # Con C.I:5918362", "2.- ROBERTA HUMACAYA MAMANI, con C.I: 5932821").
            #
            # Palabras de tres letras o más: el texto llega todo en mayúsculas,
            # así que sin ese mínimo la prosa que a veces se mete entre el nombre
            # y la cédula ("mayor de edad, con C.I.") pasaba por nombre. Cuando
            # la cédula no sigue al nombre el campo queda vacío, que es lo que
            # corresponde -- un nombre inventado nadie lo vuelve a mirar.
            #
            # El tratamiento queda fuera del nombre: la minuta nombra a la misma
            # persona suelta al enumerarla y "el señor Fulano" más adelante, y sin
            # descartarlo entraban las dos como si fueran dos poseedores. Ñ llega
            # como N, que es lo que hace normalize().
            r"\b(?:(?:EL|LA|LOS|LAS)\s+)?"
            r"(?:(?:SENOR(?:A|ES|AS)?|SRA?|DON|DONA|DR|DRA|LIC|ING|ARQ)\.?\s+)?"
            rf"([A-Z]{{3,}}(?:\s+[A-Z]{{3,}}){{1,3}})[,.\s]+CON {_ID_CARD}",
        ),
    ),
    DocumentField(
        "statement_dates",
        "Fecha de la declaración jurada",
        printed=("FECHA", "FECHAS"),
        patterns=spanish_dates.PATTERNS,
        transform="spanish_date",
    ),
)


# Keyed by (carpeta, document): the same document read inside two carpetas can
# be asked for different values, which is the whole point of the catalogue.
# A pair with nothing here is read with the generic OCR and stays at its text,
# its labelled values and its cuadros.
DOCUMENT_FIELDS: Dict[Tuple[str, str], Tuple[DocumentField, ...]] = {
    (POSSESSORS_KEY := "possessors", DocumentType.PLAN): (
        DocumentField(
            "cadastral_code",
            "Código catastral",
            printed=("CODIGO CATASTRAL", "COD CATASTRAL", "COD. CATASTRAL"),
            # 00-33-432-012-0-00-000-000, with whatever the OCR made of the dashes.
            patterns=(
                r"(\d{2}\s*[-.]\s*\d{2}\s*[-.]\s*[0-9A-Z]{3}\s*[-.]\s*\d{3}\s*[-.]\s*\d\s*[-.]\s*\d{2}\s*[-.]\s*\d{3}\s*[-.]\s*\d{3})",
            ),
        ),
        # What the sheet copies from the IDE: filled from the lookup of the code.
        # The address and the colindancias are read under the croquis from the IDE
        # (PossessorsPlanLookup), not from the sheet: they feed the carpeta but are
        # not asked here.
        DocumentField("street", "Dirección / calle", from_ide=True, hidden=True),
        DocumentField("boundaries", "Colindancias", from_ide=True, hidden=True),
        # What the sheet says about the streets it faces is their width ("CALLE DE
        # 12.50 MTS." next to the lote, "Calle de 9.00 mts." in the VIA box).
        DocumentField(
            "street_width",
            "Ancho de calle",
            patterns=(r"CALLE\s*DE\s*(\d+(?:[.,]\d+)?)\s*(?:MTS?|M)\b",),
            collect_all=True,
            transform="metres",
        ),
        # Only the predio the plano says it is: whether it is the one of the code is
        # what the table under the croquis checks against the IDE.
        DocumentField(
            "property_number",
            "Número de predio",
            # Not read by label: a plano whose lote is blank ("LOTE N°" with nothing
            # after it) would give back "N°" as the number.
            # The ubicación box: "MANZANO 432 LOTE 002" (the manzana may be "B37", the
            # separators dots). "LOTE N: 5" of the drawing has no digits right after the
            # word and is not it. Then the lot the drawing writes over its own surface
            # ("LOTE N° 002 / SUP. TOTAL UTIL"), never the neighbour's "LOTE N° 003".
            patterns=(
                r"MANZAN[AO]\W{0,8}[A-Z]?\d{1,4}\W{0,6}LOTE\W{0,8}(\d{3})",
                r"SUP\.?\s*TOTAL\s*UTIL\s*LOTE\s*N\W{0,2}\s*(\d{1,3})(?![.,\d])(?!\s*M\b)",
                r"LOTE\s*N\W{0,2}\s*(\d{1,3})(?![.,\d])(?!\s*M\b)\s*SUP\.?\s*TOTAL\s*UTIL",
                r"\bLOTE\s*(\d+)",
            ),
            transform="plain_number",
        ),
        # Measured from the UTM table by the IDE lookup when the sheet does not
        # print them: which side is on the street is what the GIS tells.
        DocumentField("frontage", "Frente", ("FRENTE",), from_ide=True),
        DocumentField("rear_frontage", "Contra frente", ("CONTRA FRENTE", "CONTRAFRENTE"), from_ide=True),
        DocumentField("depth", "Fondo", ("FONDO",), from_ide=True),
        DocumentField("depth_2", "Fondo 2", ("FONDO 2", "FONDO II", "SEGUNDO FONDO"), from_ide=True),
        DocumentField(
            "usable_area",
            "Superficie útil",
            ("SUPERFICIE UTIL", "SUP. UTIL", "SUP UTIL", "AREA UTIL", "SUPERFICIE"),
            # "SUPERFICIE TOTAL UTIL......294.66m2" (or "TTAL": the OCR drops letters). It must
            # end in m2: "SUP. TOTAL UTIL" followed by a "30.18m" side is not the surface.
            patterns=(r"SUP(?:ERFICIE|\.)?\s*(?:T[A-Z]{2,4}\s+)?UTIL\W{0,40}?(\d[\d.,]*\s*M[2²])",),
        ),
    ),
    (POSSESSORS_KEY, DocumentType.SWORN_STATEMENT): NOTARIAL_FIELDS,
    # El acta notarial llega clasificada unas veces como declaración jurada y
    # otras como formulario, y es la misma hoja: se le saca lo mismo.
    (POSSESSORS_KEY, DocumentType.FORM): NOTARIAL_FIELDS,
}


def document_fields(folder_type_key: Optional[str], doc_type: str) -> Tuple[DocumentField, ...]:
    """What to pull out of a document of this type inside a carpeta of that kind."""
    return DOCUMENT_FIELDS.get((folder_type(folder_type_key).key, doc_type), ())
