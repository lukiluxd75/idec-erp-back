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

Nothing is guessed. A label that is not on the sheet comes back empty and is
named in the observations, so the architect sees what to type instead of finding
out later that a field was silently filled with the wrong thing.

Pure: it only touches the reading it is given (CLAUDE.md §3).
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.domains.folder_analysis.domain.services.text import clean_value, compact, normalize

# What is kept of the line that follows a label found in the running text. Longer
# than this is a sentence that happened to start with the word, not a value.
MAX_TEXT_VALUE_CHARS = 80

# A measurement as it is written on a plano: "12.50", "12,50 m", "240 m2".
_MEASURE = re.compile(r"^[0-9][0-9.,]*\s*(?:M2|M²|MTS|MT|M)?\b", re.IGNORECASE)
_FIRST_NUMBER = re.compile(r"\d+")


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
        # Walk the line until as many letters and digits as the label have gone
        # by: that is where its value starts, whatever punctuation sits in
        # between ("FRENTE: 12,50" and "FRENTE . 12,50" alike).
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
    # A measurement ends where the number ends: the rest of the line is another
    # note that happens to sit next to it on the sheet.
    return (measure.group(0) if measure else cleaned[:MAX_TEXT_VALUE_CHARS]).strip() or None


def harvest(
    reading: Dict[str, Any], specs: Sequence[Any]
) -> Tuple[Dict[str, Optional[str]], List[str]]:
    """The values found for `specs`, and the labels that were not on the sheet.

    `specs` are DocumentField (domain/folder_types.py): the key to store the
    value under, the label the screen shows and how it comes printed.
    """
    pairs = _labelled_pairs(reading)
    lines = _lines(reading.get("full_text") or "")
    found: Dict[str, str] = {}
    taken: set = set()
    used_lines: set = set()

    # The pairs the OCR already separated are the sure thing, and an exact label
    # beats one that only starts the same way. Only then is the body of the
    # sheet searched, which is where a plano writes its measurements.
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

    values = {spec.key: _shaped(spec, found.get(spec.key)) for spec in specs}
    missing = [spec.label for spec in specs if not values[spec.key]]
    return values, missing


def _shaped(spec: Any, value: Optional[str]) -> Optional[str]:
    """What is stored: the value as printed, or only its number when the field
    is the one the office asks for by number (the notary)."""
    if value and getattr(spec, "number_only", False):
        number = _FIRST_NUMBER.search(value)
        return number.group(0) if number else value
    return value


def observation(missing: Iterable[str]) -> Optional[str]:
    names = list(missing)
    if not names:
        return None
    return (
        "No se encontraron en la hoja, quedaron vacíos para cargar a mano: " + ", ".join(names) + "."
    )
