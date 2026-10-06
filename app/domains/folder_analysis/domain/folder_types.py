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
    # The line under the field: where to copy it from, or what the office's rule for it is.
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
        hint="Carril retirado. Solo para los documentos guardados antes de quitarlo.",
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
    description="Trámite de poseedores: avalúo, plano, formulario y otros documentos.",
    document_types=(
        DocumentType.APPRAISAL,
        DocumentType.PLAN,
        DocumentType.FORM,
        DocumentType.ID_CARD,
    ),
    field_groups=(
        FolderFieldGroup(
            key="notarial",
            title="Datos del formulario",
            fields=(
                FolderField(
                    key="notary_number",
                    label="N.º de notario",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.FORM,
                    hint="Se extrae del sello notarial del formulario.",
                ),
                FolderField(
                    key="owner_name",
                    label="Poseedores",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.FORM,
                    hint="Nombres de los poseedores declarados en el formulario.",
                ),
                FolderField(
                    key="statement_dates",
                    label="Fecha de la declaración jurada",
                    source=FieldSource.DOCUMENT,
                    from_document=DocumentType.FORM,
                    hint="La fecha se guarda en formato dd/mm/aaaa.",
                ),
            ),
        ),
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
    ),
)


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
    # The office asks for this one by number, not by name (the notary), so only the number of what was read is kept.
    number_only: bool = False
    patterns: Tuple[str, ...] = ()
    # Cómo viene escrito el valor DENTRO del sello, para un campo que vive en la estampa redonda y no en la redacción.
    seal_patterns: Tuple[str, ...] = ()
    # Post-processing of what the pattern matched.
    transform: Optional[str] = None
    from_ide: bool = False
    hidden: bool = False
    # Every match of every pattern, not just the first: a plano prints the width of each street it faces.
    collect_all: bool = False
    item_label: Optional[str] = None
    # La redacción que, cuando viene justo ANTES de lo que un patrón encontró, dice que ese número es de otra cosa.
    rejected_after: Tuple[str, ...] = ()
    # Qué pedirle al modelo de visión mirando la foto, en castellano y señalando dónde está el valor en la hoja.
    vision_hint: Optional[str] = None


# Cómo viene escrita la cédula detrás de un nombre.
_ID_CARD = r"(?:CEDULA DE IDENTIDAD|C\.?\s?[IL1]\.?)"

# La cédula con su número detrás.
_ID_NUMBER = rf"{_ID_CARD}[^\d]{{0,6}}\d"

# El código catastral, en las dos formas en que lo imprimen estas hojas.
#
# El plano lo escribe con 19 dígitos ("00-33-432-012-0-00-000-000") y el avalúo
# con 17 ("33-432-012-0-00-000-000"): es el mismo predio, y el par de adelante no
# es parte del código -- es lo que ya decía cadastral_code.to_gis_code(), que
# acepta las dos. Por eso el primer grupo es opcional y no hay dos patrones.
# "SUPERFICIE TOTAL UTIL......294.66m2", "Sup. Total Util 299.02 m2" (o "TTAL":
# el OCR se come letras). Tiene que terminar en m2: un "SUP. TOTAL UTIL" seguido
# de un lado de 30.18m no es la superficie.
_USABLE_AREA = r"SUP(?:ERFICIE|\.)?\s*(?:T[A-Z]{2,4}\s+)?UTIL\W{0,40}?(\d[\d.,]*\s*M[2\u00b2])"

_CODE_SEP = r"\s*[-.]\s*"
_CADASTRAL_CODE = (
    rf"\b((?:\d{{2}}{_CODE_SEP})?\d{{2}}{_CODE_SEP}[0-9A-Z]{{3}}{_CODE_SEP}\d{{3}}"
    rf"{_CODE_SEP}\d{_CODE_SEP}\d{{2}}{_CODE_SEP}\d{{3}}{_CODE_SEP}\d{{3}})(?![\d-])"
)

_NOT_NAME = (
    "PRESENTE|PRESENTES|PRESENTO|PRESENTA|PRESENTAN|PRESENTARON|PRESENTAR"
    "|HIZO|HICIERON|HACE|HACEN"
    "|COMPARECE|COMPARECEN|COMPARECIO|COMPARECIERON|COMPARECIENTE|COMPARECIENTES"
    "|APERSONA|APERSONAN|SUSCRIBE|SUSCRIBEN|DECLARA|DECLARAN|DECLARANTE|DECLARANTES"
    "|SOLICITANTE|SOLICITANTES|POSEEDOR|POSEEDORA|PROPIETARIO|PROPIETARIA"
    "|MAYOR|MENOR|EDAD|ANOS|ANO|HABIL|HABILES|VECINO|VECINA"
    "|BOLIVIANO|BOLIVIANA|SOLTERO|SOLTERA|CASADO|CASADA|VIUDO|VIUDA"
    "|DIVORCIADO|DIVORCIADA|CONVIVIENTE|ESTADO|CIVIL"
    "|PROFESION|OCUPACION|DOMICILIO|DOMICILIADO|DOMICILIADA|DIRECCION"
    "|CEDULA|IDENTIDAD|CARNET|NUMERO|NRO|CODIGO|CATASTRAL"
    "|ANTE|NOTARIO|NOTARIA|NOTARIAL|PUBLICA|PUBLICO|ABOGADO|ABOGADA|FE"
    "|SENOR|SENORA|SENORES|SENORITA|DON|DONA|SR|SRA|SRES|DR|DRA|LIC|ING|ARQ"
    "|NOMBRE|NOMBRES|FIRMA|FIRMAS|HUELLA|HUELLAS|FORMULARIO|DECLARACION|DECLARACIONES"
    "|MUNICIPIO|DEPARTAMENTO|ESTADO|PLURINACIONAL|GOBIERNO|AUTONOMO|MUNICIPAL"
    "|CON|SIN|POR|PARA|SEGUN|SOBRE|ENTRE|DESDE|HASTA"
    "|QUIEN|QUIENES|AMBOS|AMBAS|CONJUNTAMENTE|CONMIGO|MISMO|MISMA"
    "|DEL|DE|LA|EL|LO|LOS|LAS|UN|UNA|Y|O|SU|SUS|EN|AL|A|QUE|SE|MI|ME|NI"
)
_NOT_A_NAME = rf"(?!(?:{_NOT_NAME})\b)"

# Una palabra de un nombre: dos letras o más y ninguna de las de arriba.
_NAME_WORD = rf"\b{_NOT_A_NAME}[A-Z]{{2,}}"

# Los enlaces que SÍ van dentro de un apellido ("MARIA DE LA CRUZ PEREZ").
_NAME_LINK = r"(?:DE|DEL|LA|LAS|LOS|Y|DA|DOS)"

# Un nombre completo: de dos a cinco palabras, con sus enlaces.
_NAME = rf"{_NAME_WORD}(?:\s+(?:{_NAME_LINK}\s+){{0,2}}{_NAME_WORD}){{1,4}}"

# La prosa que un acta mete ENTRE el nombre y su cédula ("NOELIA ALMENDRAS RODRIGUEZ, boliviana, mayor de edad, con C.I.
_BETWEEN = rf"(?:[\s,.;-]+(?:{_NOT_NAME})\b)*"


# Lo que se le saca a un acta notarial.
NOTARIAL_FIELDS: Tuple["DocumentField", ...] = (
    DocumentField(
        "notary_number",
        "Notario (Nº)",
        printed=("NOTARIA DE FE PUBLICA", "NOTARIA", "NOTARIO"),
        number_only=True,
        patterns=(
            r"NOTARI[AO]\s*DE\s*FE[A-Z\s,.-]{0,40}?(?:NRO|N[O0°])\.?\s*(\d{1,3})\b",
        ),
        seal_patterns=(
            # "NOTARIA DE FE PUBLICA No.
            r"(?:NRO|N[O0°])\.?\s*(\d{1,3})\b",
            # El sello con la marca a secas, que es como sale impreso en el medio de muchos: "N 37" bajo "NOTARIA DE FE PUBLICA".
            r"\bN\s*\.?\s*(\d{1,3})\b",
            # El sello al que el OCR le comió la marca: "DE PRIMERA CLASE 48".
            r"CLASE\s*(\d{1,3})\b",
        ),
        rejected_after=("RESOLUCION MINISTERIAL", "RESOLUCION", "MINISTERIAL", "R.M."),
        vision_hint=(
            "el número de la notaría, que está DENTRO del sello redondo estampado en la hoja "
            '(dice "NOTARIA DE FE PUBLICA" alrededor y el número en el medio, por ejemplo "Nº 37"). '
            "Devuelva solo el número. NUNCA el número de la Resolución Ministerial impresa bajo el "
            'título "FORMULARIO NOTARIAL" (por ejemplo "Resolución Ministerial Nº 57/2020"), que no '
            "es el notario; ni el número de la cédula, ni el del trámite, ni una fecha."
        ),
    ),
    DocumentField(
        "owner_name",
        "Nombres de los poseedores",
        printed=("NOMBRE DEL PROPIETARIO", "PROPIETARIO", "DECLARANTE"),
        collect_all=True,
        item_label="Poseedor",
        patterns=(
            # El nombre que lleva su cédula detrás, que es como lo escriben todas estas hojas.
            rf"({_NAME}){_BETWEEN}[\s,.;-]*\bCON\s+{_ID_NUMBER}",
            # La hoja que presenta al declarante y no le escribe la cédula al lado.
            rf"\bSE\s+HI(?:ZO|CIERON)\s+PRESENTES?\b[\s,:.;-]+({_NAME})",
            rf"\bSE\s+PRESENT(?:O|ARON|A|AN)\b[\s,:.;-]+({_NAME})",
            rf"\bCOMPAREC(?:E|EN|IO|IERON)\b[\s,:.;-]+({_NAME})",
            rf"({_NAME})[\s,.;-]*{_ID_NUMBER}",
        ),
        vision_hint=(
            "el nombre completo de cada poseedor que declara o comparece, tal como está escrito y en "
            "el orden en que aparecen, separados por coma. Son los que la hoja presenta con "
            '"se hizo presente", "compareció" o "declara", y los que llevan su cédula de identidad al '
            "lado; el mismo nombre vuelve a estar en la tabla de firmas del pie, bajo "
            '"Nombre". NUNCA el notario, aunque su nombre esté primero y en mayúsculas (va detrás de '
            '"ANTE MÍ" y lleva "Notario de Fe Pública" al lado), ni el abogado, ni los testigos, ni '
            "los colindantes. Solo el nombre: sin el tratamiento (señor, señora), sin la "
            "nacionalidad, sin el estado civil y sin la profesión."
        ),
    ),
    DocumentField(
        "statement_dates",
        "Fecha de la declaración jurada",
        printed=("FECHA", "FECHAS"),
        patterns=spanish_dates.PATTERNS,
        transform="spanish_date",
        vision_hint=(
            "la fecha en que se hizo esta declaración, SIEMPRE en dd/mm/aaaa (por ejemplo "
            "21/09/2026). Está en el párrafo que abre el acto y puede venir escrita de cualquiera "
            'de estas formas: con letras ("del día, lunes veintiún del mes de septiembre del año '
            'dos mil veintiséis", "Lunes veinte y uno del mes de septiembre del dos mil '
            'veintiséis", "a los doce días del mes de marzo de dos mil veinticinco") o con cifras '
            '("21 de septiembre de 2026", "21/09/2026"). Venga como venga, devuélvala en cifras. '
            "NUNCA la fecha chica que está dentro del sello redondo (es la del nombramiento del "
            "notario), ni el año de la Resolución Ministerial del encabezado, ni la fecha de un "
            "documento anterior citado en el texto, ni la hora."
        ),
    ),
)


DOCUMENT_FIELDS: Dict[Tuple[str, str], Tuple[DocumentField, ...]] = {
    (POSSESSORS_KEY := "possessors", DocumentType.PLAN): (
        DocumentField(
            "cadastral_code",
            "Código catastral",
            printed=("CODIGO CATASTRAL", "COD CATASTRAL", "COD. CATASTRAL"),
            patterns=(_CADASTRAL_CODE,),
        ),
        # What the sheet copies from the IDE: filled from the lookup of the code.
        DocumentField("street", "Dirección / calle", from_ide=True, hidden=True),
        DocumentField("boundaries", "Colindancias", from_ide=True, hidden=True),
        DocumentField(
            "street_width",
            "Ancho de calle",
            patterns=(r"CALLE\s*DE\s*(\d+(?:[.,]\d+)?)\s*(?:MTS?|M)\b",),
            collect_all=True,
            item_label="Calle",
            transform="metres",
        ),
        DocumentField(
            "property_number",
            "Número de predio",
            # Not read by label: a plano whose lote is blank ("LOTE N°" with nothing after it) would give back "N°" as the number.
            patterns=(
                r"MANZAN[AO]\W{0,8}[A-Z]?\d{1,4}\W{0,6}LOTE\W{0,8}(\d{3})",
                r"SUP\.?\s*TOTAL\s*UTIL\s*LOTE\s*N\W{0,2}\s*(\d{1,3})(?![.,\d])(?!\s*M\b)",
                r"LOTE\s*N\W{0,2}\s*(\d{1,3})(?![.,\d])(?!\s*M\b)\s*SUP\.?\s*TOTAL\s*UTIL",
                r"\bLOTE\s*(\d+)",
            ),
            transform="plain_number",
        ),
        DocumentField("frontage", "Frente", ("FRENTE",), from_ide=True),
        DocumentField("rear_frontage", "Contra frente", ("CONTRA FRENTE", "CONTRAFRENTE"), from_ide=True),
        DocumentField("depth", "Fondo", ("FONDO",), from_ide=True),
        DocumentField("depth_2", "Fondo 2", ("FONDO 2", "FONDO II", "SEGUNDO FONDO"), from_ide=True),
        DocumentField(
            "usable_area",
            "Superficie útil",
            ("SUPERFICIE UTIL", "SUP. UTIL", "SUP UTIL", "AREA UTIL", "SUPERFICIE"),
            patterns=(_USABLE_AREA,),
        ),
    ),
    (POSSESSORS_KEY, DocumentType.FORM): NOTARIAL_FIELDS,
    # El avalúo ("Formulario para actualización de datos técnicos") no identifica
    # al predio por su matrícula --su casilla de información legal suele decir "No
    # registra"-- sino por el código catastral, impreso grande en la cabecera. Es
    # el mismo código del plano, sin el par de adelante.
    (POSSESSORS_KEY, DocumentType.APPRAISAL): (
        DocumentField(
            "usable_area",
            "Superficie útil",
            # Sin "SUPERFICIE" a secas, a diferencia del plano: esta hoja imprime
            # "Superficie Lote: 294.66" en su cuadro de descripción, que es el área
            # del lote y NO la útil. La útil va escrita sobre el croquis
            # ("Sup. Total Util 299.02 m2") y es la que pide la carpeta.
            printed=(
                "SUPERFICIE TOTAL UTIL",
                "SUP TOTAL UTIL",
                "SUPERFICIE UTIL",
                "SUP. UTIL",
                "SUP UTIL",
                "AREA UTIL",
            ),
            patterns=(_USABLE_AREA,),
            vision_hint=(
                'la superficie útil total del lote, escrita SOBRE el croquis del predio ("Sup. '
                'Total Util 299.02 m2"). Devuélvala con sus unidades. NUNCA la "Superficie Lote" '
                "del cuadro de descripción, que es otra; ni los metros de una construcción del "
                "cuadro de características; ni la medida de un lado del croquis."
            ),
        ),
        DocumentField(
            "cadastral_code",
            "Código catastral",
            # En esta hoja el rótulo va DEBAJO del número, como pie; por eso lo que
            # lo encuentra es el patrón y no la etiqueta. Las etiquetas quedan para
            # la hoja que sí lo rotula al lado.
            printed=("CODIGO CATASTRAL", "COD CATASTRAL", "COD. CATASTRAL"),
            patterns=(_CADASTRAL_CODE,),
            vision_hint=(
                "el código catastral, impreso grande en la cabecera de la hoja, con el rótulo "
                '"Código catastral" DEBAJO del número. Son siete grupos de cifras separados por '
                'guión ("33-432-012-0-00-000-000"). NUNCA el "# Inmueble", ni el "Formulario No.", '
                'ni el "Código" alfanumérico de la derecha, ni el número de cédula.'
            ),
        ),
    ),
}


def document_fields(folder_type_key: Optional[str], doc_type: str) -> Tuple[DocumentField, ...]:
    """What to pull out of a document of this type inside a carpeta of that kind."""
    return DOCUMENT_FIELDS.get((folder_type(folder_type_key).key, doc_type), ())
