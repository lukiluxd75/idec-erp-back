"""
Pulls the values a carpeta needs out of a sheet that was read with the generic
OCR (its text, its "ETIQUETA: valor" pairs and its cuadros).

A folio and a comprobante are forms: their parsers know the layout and read them
box by box. A plano or a declaración jurada are not -- what is printed on them
and where changes from one draughtsman and one notary to the next -- so there is
no layout to follow, only the label next to the value. That is what this does:
for each field the carpeta asks for, it looks for the label as it is printed
(`printed`), first among the pairs the OCR already separated and then in the
text of the sheet.

A value that is not written on the sheet but stamped on it -- the number of the
notary, which lives in the seal -- comes in through from_seals(), with the text
of each seal read apart from the page (see SealReadingPort).

Nothing is guessed. A label that is not on the sheet comes back empty and is
named in the observations, so the architect sees what to type instead of finding
out later that a field was silently filled with the wrong thing.

Pure: it only touches the reading it is given (CLAUDE.md §3).
"""
import re
from re import error as RegexError
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.domains.folder_analysis.domain.services import spanish_dates
from app.domains.folder_analysis.domain.services.text import clean_value, compact, normalize

# What is kept of the line that follows a label found in the running text.
MAX_TEXT_VALUE_CHARS = 80

# A measurement as it is written on a plano: "12.50", "12,50 m", "240 m2".
_MEASURE = re.compile(r"^[0-9][0-9.,]*(?![/-]\d)\s*(?:M2|M²|MTS|MT|M)?\b", re.IGNORECASE)
_FIRST_NUMBER = re.compile(r"\d+")


def _spanish_date(match: "re.Match") -> Optional[str]:
    parts = match.groupdict()
    return spanish_dates.to_iso_like(
        parts.get("day", ""), parts.get("month", ""), parts.get("year", "")
    )


def _plain_number(match: "re.Match") -> Optional[str]:
    # "002" is lote 2: the draughtsmen pad the number and the GIS does not.
    return str(int(match.group(1)))


def _metres(match: "re.Match") -> Optional[str]:
    # The width of a street as the carpeta writes it: "12,50" -> "12.50 m".
    return f"{match.group(1).replace(',', '.')} m"


# What a field can ask to be done with what its pattern matched.
TRANSFORMS = {
    "spanish_date": _spanish_date,
    "plain_number": _plain_number,
    "metres": _metres,
}


# Cuánto texto se mira hacia atrás para saber de qué habla el número que un patrón encontró.
REJECT_WINDOW_CHARS = 30


def _rejected(text: str, start: int, spec: Any) -> bool:
    """¿Lo que viene justo antes dice que este número es de otra cosa?

    Un formulario notarial imprime "Resolución Ministerial Nº 57/2020" a un
    centímetro del sello, y esa marca de número se lee igual que la del sello. El
    número de la resolución es el mismo en todos los formularios: tomarlo por el
    del notario no es un valor flojo, es un valor de otro campo.

    Se mira lo que precede al VALOR, no a la frase que lo encontró: el rótulo
    "NOTARIA DE FE PUBLICA" del sello y el número de la resolución pueden estar en
    la misma línea, con el estorbo en el medio.
    """
    phrases = getattr(spec, "rejected_after", ())
    if not phrases:
        return False
    before = text[max(0, start - REJECT_WINDOW_CHARS) : start]
    return any(phrase in before for phrase in phrases)


def _value_start(match: "re.Match") -> int:
    """Dónde empieza lo que el patrón capturó. Un patrón que usa grupos con
    nombre (una fecha en letras) no tiene grupo 1, y ahí lo que vale es el
    comienzo de la coincidencia entera."""
    try:
        start = match.start(1)
    except (IndexError, RegexError):
        return match.start()
    return start if start >= 0 else match.start()


def _from_patterns(text: str, spec: Any, patterns: Optional[Sequence[str]] = None) -> Optional[str]:
    """The value written inside a sentence, for a sheet that has no labels.

    A notarial act names nothing: the number of the notary, the person and the
    date are inside its prose, and what identifies them is the wording around
    them. Searched on the whole normalized text -- one line, so a sentence that
    wraps is still one sentence.

    The patterns are an order of preference, not a set: the first one that says
    anything answers, because a field lists them from the wording that names it
    most surely down to the one that only usually does.

    `patterns` replaces the field's own list, for a reading that is not the text
    of the sheet and has its own wording -- the text of a seal (`seal_patterns`).
    """
    transform = TRANSFORMS.get(getattr(spec, "transform", None))
    collect_all = getattr(spec, "collect_all", False)
    for pattern in getattr(spec, "patterns", ()) if patterns is None else patterns:
        if not collect_all:
            for match in re.finditer(pattern, text):
                if _rejected(text, _value_start(match), spec):
                    continue
                value = transform(match) if transform else clean_value(match.group(1))
                if value:
                    return value
            continue
        # Every match of THIS pattern -- a plano faces more than one street and a minuta lists more than one poseedor.
        values: List[str] = []
        for found in re.finditer(pattern, text):
            if _rejected(text, _value_start(found), spec):
                continue
            value = transform(found) if transform else clean_value(found.group(1))
            if value and value not in values:
                values.append(value)
        if values:
            return ", ".join(values)
    return None


def _labelled_pairs(reading: Dict[str, Any]) -> List[Tuple[str, str]]:
    """The "ETIQUETA: valor" pairs of every page, in reading order."""
    pairs: List[Tuple[str, str]] = []
    for page in reading.get("pages") or []:
        for field in page.get("fields") or []:
            name, value = field.get("name"), field.get("value")
            if name and value:
                pairs.append((compact(name), value))
    return pairs


def _ends_the_label(text: str, position: int) -> bool:
    """Whether the label really ends where it was matched.

    Letters and digits alone cannot tell "FONDO 2" from "FONDO" followed by a
    measurement of 25 metres: both read FONDO2... So the label only counts as
    finished when what follows is not another letter or digit -- "FONDO 2 24.80"
    is the second fondo, "FONDO 25.00" is the first one and its value.
    """
    return position >= len(text) or not text[position].isalnum()


def _aliases(specs: Sequence[Any]) -> List[Tuple[Any, str]]:
    """Every (field, label) pair, the longest label first.

    The order is what keeps "FONDO 2" from being read as the "FONDO" of the lot:
    the longer label claims its pair before the shorter one gets to look at it.
    """
    pairs = [(spec, compact(printed)) for spec in specs for printed in spec.printed]
    return sorted((p for p in pairs if p[1]), key=lambda pair: len(pair[1]), reverse=True)


def _from_pairs(pairs: List[Tuple[str, str]], alias: str, taken: set, exact: bool) -> Optional[int]:
    for index, (name, _value) in enumerate(pairs):
        if index in taken:
            continue
        if name == alias:
            return index
        if not exact and name.startswith(alias) and _ends_the_label(name, len(alias)):
            return index
    return None


def _lines(text: str) -> List[str]:
    """The sheet cut into lines and normalized one by one.

    Split BEFORE normalizing: normalize() collapses every run of whitespace,
    newlines included, and would leave the whole sheet on a single line.
    """
    return [line for line in (normalize(raw) for raw in (text or "").splitlines()) if line]


def _from_text(lines: Sequence[str], alias: str, used: set) -> Optional[Tuple[str, int]]:
    """The label written in the body of the sheet, with what follows it, and the
    line it was found on (so a longer label does not lend its line to a shorter
    one: "FONDO 2 24.80" is not where "FONDO" gets its value from)."""
    for index, line in enumerate(lines):
        if index in used or not compact(line).startswith(alias):
            continue
        seen = 0
        for position, char in enumerate(line):
            if seen == len(alias):
                if not _ends_the_label(line, position):
                    break
                value = _cut(line[position:])
                if value:
                    return value, index
                break
            if char.isalnum():
                seen += 1
    return None


def _cut(value: str) -> Optional[str]:
    cleaned = clean_value(value)
    if not cleaned:
        return None
    measure = _MEASURE.match(cleaned)
    return (measure.group(0) if measure else cleaned[:MAX_TEXT_VALUE_CHARS]).strip() or None


def harvest(
    reading: Dict[str, Any], specs: Sequence[Any]
) -> Tuple[Dict[str, Optional[str]], List[str]]:
    """The values found for `specs`, and the labels that were not on the sheet.

    `specs` are DocumentField (domain/folder_types.py): the key to store the
    value under, the label the screen shows and how it comes printed.
    """
    pairs = _labelled_pairs(reading)
    text = reading.get("full_text") or ""
    lines = _lines(text)
    prose = normalize(text)
    found: Dict[str, str] = {}
    taken: set = set()
    used_lines: set = set()

    for spec in specs:
        value = _from_patterns(prose, spec)
        if value:
            found[spec.key] = value

    # The pairs the OCR already separated are the sure thing, and an exact label beats one that only starts the same way.
    for exact in (True, False):
        for spec, alias in _aliases(specs):
            if spec.key in found:
                continue
            index = _from_pairs(pairs, alias, taken, exact)
            if index is not None:
                value = clean_value(pairs[index][1])
                if value:
                    found[spec.key] = value
                    taken.add(index)

    for spec, alias in _aliases(specs):
        if spec.key in found:
            continue
        hit = _from_text(lines, alias, used_lines)
        if hit:
            found[spec.key], line_index = hit
            used_lines.add(line_index)

    values = {spec.key: _shaped(spec, _as_written(spec, found.get(spec.key))) for spec in specs}
    return values, missing_labels(values, specs)


def missing_labels(values: Mapping[str, Optional[str]], specs: Sequence[Any]) -> List[str]:
    """The labels that stayed empty and have to be typed by hand.

    What comes from the IDE does not count: the sheet does not print it, so its
    absence is not something the reading failed at. Public because what is
    missing is asked again after the seals were read -- a value the stamp gave is
    not missing any more.
    """
    return [
        spec.label
        for spec in specs
        if not values.get(spec.key) and not getattr(spec, "from_ide", False)
    ]


def from_seals(texts: Iterable[str], specs: Sequence[Any]) -> Dict[str, str]:
    """What the seals stamped on the sheet say, for the fields that live in one.

    A seal is not read with the text of the page: its legend is curved and the
    OCR of the whole sheet gives it back in pieces, so it is found in the image,
    cropped and unwrapped apart (SealReadingPort). Here it arrives as text
    already, one reading per element, and each field looks for its value with the
    patterns it declared for the seal (`seal_patterns`).

    `texts` is consumed one by one and dropped as soon as every one of those
    fields is filled: each reading costs a call to the OCR, and the seal is
    almost always on the first sheet. Only what was found comes back -- a seal
    that says nothing leaves the field to the text of the sheet.
    """
    wanted = [spec for spec in specs if getattr(spec, "seal_patterns", ())]
    found: Dict[str, str] = {}
    if not wanted:
        return found
    for text in texts:
        prose = normalize(text)
        for spec in wanted:
            if spec.key in found:
                continue
            value = _shaped(spec, _from_patterns(prose, spec, spec.seal_patterns))
            if value:
                found[spec.key] = value
        if len(found) == len(wanted):
            break
    return found


def vision_wanted(specs: Sequence[Any], values: Mapping[str, Optional[str]]) -> List[Any]:
    """Los campos que vale la pena mirar en la foto con el modelo de visión.

    Dos clases, y nada más, porque cada foto cuesta medio minuto de una
    computadora de los arquitectos:
      - el que vive en un sello (`seal_patterns`): ahí el texto de la hoja no es
        confiable aunque haya dicho algo. El número del notario está estampado en
        una corona curva, encimado al título, y al lado está impresa la
        "Resolución Ministerial Nº 57/2020", que se lee igual de bien. Mirar la
        foto es lo único que distingue uno de otro, así que se pregunta siempre.
      - el que quedó vacío: el OCR no lo encontró y la alternativa es que el
        arquitecto lo copie a mano.
    Un campo que ya tiene valor y no vive en un sello no se pregunta: lo que el
    texto leyó bien no se manda a revisar a un modelo.
    """
    return [
        spec
        for spec in specs
        if getattr(spec, "vision_hint", None)
        and (getattr(spec, "seal_patterns", ()) or not values.get(spec.key))
    ]


def from_vision(answer: Mapping[str, Any], specs: Sequence[Any]) -> Dict[str, str]:
    """Lo que el modelo contestó de la foto, pasado por la misma forma que el
    resto de la lectura (del notario se guarda su número y nada más).

    Solo las claves pedidas: un modelo que agrega campos de su cosecha no entra
    en la carpeta. Lo vacío, el null y el "[ilegible]" con que se le pidió marcar
    lo que no se ve quedan afuera -- un campo que la foto no muestra se queda
    vacío, que es lo honesto.
    """
    found: Dict[str, str] = {}
    for spec in specs:
        raw = answer.get(spec.key)
        if raw is None or isinstance(raw, (dict, list, bool)):
            continue
        value = clean_value(str(raw))
        if not value or "ILEGIBLE" in normalize(value):
            continue
        shaped = _shaped(spec, _as_written(spec, value))
        if shaped:
            found[spec.key] = shaped
    return found


def _as_written(spec: Any, value: Optional[str]) -> Optional[str]:
    """Lo que contestó el modelo, en la forma en que la oficina guarda ese campo.

    Una fecha va en dd/mm/aaaa y nada más. Al modelo se le pide así, y casi
    siempre la devuelve así, pero también la devuelve como la leyó de la hoja
    ("21 de septiembre de 2026") o con el año adelante: eso se pasa a la forma de
    la oficina acá, en vez de guardar tres formas distintas de la misma fecha
    según qué computadora contestó. Una que no se entienda se descarta, como
    cualquier otra respuesta que no se puede leer.
    """
    if value and getattr(spec, "transform", None) == "spanish_date":
        return spanish_dates.any_date(value)
    return value


def _shaped(spec: Any, value: Optional[str]) -> Optional[str]:
    """What is stored: the value as printed, or only its number when the field
    is the one the office asks for by number (the notary).

    A field asked for by number and matched to something with no digits in it is
    not that field: the heading "NOTARIO" of a minuta lends its line to "DE FE
    PUBLICA", which was stored as if it were the number of the notary. Empty is
    the honest answer -- it is named in the observations and typed by hand,
    instead of reaching the carpeta sheet looking like a reading.
    """
    if value and getattr(spec, "number_only", False):
        # El primer número que no sea de otra cosa.
        prose = normalize(value)
        for number in _FIRST_NUMBER.finditer(prose):
            if not _rejected(prose, number.start(), spec):
                return number.group(0)
        return None
    return value


def observation(missing: Iterable[str]) -> Optional[str]:
    names = list(missing)
    if not names:
        return None
    return (
        "No se encontraron en la hoja, quedaron vacíos para cargar a mano: " + ", ".join(names) + "."
    )
