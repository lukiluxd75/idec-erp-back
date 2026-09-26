"""
Reads a Bolivian municipal property tax receipt (FUR - COMPROBANTE DE PAGO,
IMPBI / RUAT) from the OCR of its photo, with rules instead of the vision model.

The FUR is a printed form: every value sits with a fixed label, so the rules are
the same steps for every field:

  1. find the label ("BASE IMPONIBLE", "COD. CAT.", ...) allowing OCR noise --
     including the digits the OCR returns for letters ("IMPUEST0 DETERMINAD0")
  2. read the value from the first of three places that has one:
     - the rest of the label's OWN block: the service returns a label and its
       value as one block more often than not, spaces and all dropped
       ("BASEIMPONIBLE:350000.00")
     - what follows the label on its line, stopping at the next label
     - what sits under the label, for the boxes the form stacks
  3. a value that does not look like its field (an amount where an amount
     belongs) is not stored as read: the next place is tried first

Step 3 is what makes this survive a form whose layout we cannot assume: the kind
of value expected is declared per field, so a wrong place is caught instead of
stored. Whatever is still missing goes to the LLM pass, which may restructure but
never invent (the extractor only accepts values that are in this OCR text).

Confidence is the OCR's own, per field, so the review screen can mark exactly
the values the architect should compare against the photo.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.domains.folder_analysis.domain.services.text import (
    Block,
    after_label,
    clean_value,
    compact,
    group_lines,
    join_text,
    label_score,
    min_confidence,
    normalize,
)

PARSER_VERSION = 1

# A block that IS the label scores 1 or more (see text.label_score); below that
# the score is how closely it reads, and 0.85 is about one wrong character in a
# short label. Under it the field is left to the LLM pass instead of guessed at.
MIN_LABEL_SCORE = 0.85

# What a value must look like for its field, so a label's neighbour is not stored
# just because it happens to be next to it (see step 3 above).
TEXT = "text"
AMOUNT = "amount"      # 1.234,56 / 1234.56 / 0.00
AREA = "area"          # an amount, with or without its unit
INTEGER = "integer"    # a plain number (a receipt or property number)
CODE = "code"          # letters, digits and separators (a cadastral code)
DATE = "date"          # a date, possibly with its time

# Up to five decimals: that is how the UFV of the day is printed (2.68451).
_AMOUNT_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,5})?$|^\d+(?:[.,]\d{1,5})?$")
_AREA_RE = re.compile(r"^\d[\d.,]*\s*(?:M2|MTS2|METROS2)?$")
_INTEGER_RE = re.compile(r"^\d[\d.\-]*$")
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-/ ]*$")
_DATE_RE = re.compile(r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}")
# "Bs", and the box borders the OCR reads as text: never part of a value.
_NOISE = {"BS", "BS.", "SBS", "|", ":", "-"}

# key -> (labels to look for, kind of value). The order is the form's own reading
# order, which is also the order the fill log lists the fields in.
FIELDS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("collecting_entity", ("ENTIDAD RECAUDADORA", "ENTIDAD"), TEXT),
    ("correspondent", ("CORRESP.", "CORRESPONSAL"), TEXT),
    ("branch", ("SUCURSAL",), TEXT),
    ("agency", ("AGENCIA",), TEXT),
    ("cashier", ("CAJERO", "CAJA"), TEXT),
    ("folio", ("FOLIO",), CODE),
    ("paid_at", ("FECHA",), DATE),
    # "Nº INMUEBLE" reaches the parser as "NO INMUEBLE" or as "N INMUEBLE",
    # depending on which ordinal sign the form was printed with.
    ("property_number", ("NO INMUEBLE", "N INMUEBLE", "NRO INMUEBLE", "INMUEBLE NRO"), INTEGER),
    ("cadastral_code", ("COD. CAT.", "CODIGO CATASTRAL", "COD CATASTRO"), CODE),
    ("property_class", ("CLASE",), TEXT),
    ("ownership_type", ("TIPO PROPIEDAD", "TIPO DE PROPIEDAD"), TEXT),
    ("location", ("UBICACION",), TEXT),
    ("land_area", ("SUP. TERRENO", "SUPERFICIE TERRENO"), AREA),
    ("built_area", ("SUP. TOTAL CONSTRUCCION", "SUP. CONSTRUCCION", "SUPERFICIE CONSTRUCCION"), AREA),
    ("age_factor", ("FACTOR ANTIGUEDAD", "ANTIGUEDAD"), TEXT),
    ("ufv", ("UFV",), AMOUNT),
    ("taxable_base", ("BASE IMPONIBLE",), AMOUNT),
    ("assessed_tax", ("IMPUESTO DETERMINADO", "IMPUESTO"), AMOUNT),
    ("exemption", ("EXENCION",), AMOUNT),
    ("discount_10", ("DESCUENTO 10%", "DESCUENTO 10"), AMOUNT),
    ("discount_app_5", ("DESCUENTO APP 5%", "DESCUENTO APP"), AMOUNT),
    ("amount_due", ("IMPORTE A PAGAR", "IMPORTE"), AMOUNT),
    ("amount_paid", ("MONTO PAGADO", "MONTO"), AMOUNT),
    ("balance", ("SALDO GESTION", "SALDO"), AMOUNT),
)

# Labels that carry no value of their own: they are here only so a value does not
# swallow the box that follows it.
_STOP_LABELS = ("CONTRIBUYENTE", "TOTAL", "GESTION", "PROPIETARIO", "OBSERVACIONES")

_ALL_LABELS = tuple({label for _key, labels, _kind in FIELDS for label in labels} | set(_STOP_LABELS))

# The keys read out of a whole line instead of from next to a label.
LINE_FIELDS = ("receipt_type", "receipt_number", "municipality", "concept", "tax_year")


def _empty_data() -> Dict[str, Any]:
    return {
        **{key: None for key, _labels, _kind in FIELDS},
        **{key: None for key in LINE_FIELDS},
        "taxpayer": {"type": None, "id_number": None, "name": None},
    }


@dataclass
class FurReading:
    """What the rules read from the photos of one receipt."""

    data: Dict[str, Any] = field(default_factory=_empty_data)
    # Per field (dotted for the taxpayer): the OCR's own confidence in it.
    confidence: Dict[str, Optional[float]] = field(default_factory=dict)
    observations: List[str] = field(default_factory=list)
    # Per field: the label that was found, where the value was read and its raw
    # OCR text -- so a wrong value can be traced back to the rule that read it.
    trace: List[Dict[str, Any]] = field(default_factory=list)
    # The OCR text of the receipt in reading order: what the LLM pass is allowed
    # to work from, and what the JSON tab shows.
    lines: List[str] = field(default_factory=list)


def _looks_like(value: str, kind: str) -> bool:
    text = normalize(value)
    if not text:
        return False
    if kind == TEXT:
        return True
    if kind == AMOUNT:
        return bool(_AMOUNT_RE.match(text.replace(" ", "")))
    if kind == AREA:
        return bool(_AREA_RE.match(text))
    if kind == INTEGER:
        return bool(_INTEGER_RE.match(text.replace(" ", "")))
    if kind == CODE:
        return bool(_CODE_RE.match(text))
    if kind == DATE:
        return bool(_DATE_RE.search(text))
    return True


def _is_label(block: Block, labels: Sequence[str] = _ALL_LABELS) -> bool:
    """A block that is a label of the form, not somebody's value."""
    return any(label_score(block.text, label) >= 1.0 for label in labels)


def _is_noise(block: Block) -> bool:
    return normalize(block.text) in _NOISE or not compact(block.text)


def _right_of(line: Sequence[Block], label: Block) -> List[Block]:
    """The value blocks after `label` on its own line, stopping at the next label
    (the form prints several labelled boxes side by side)."""
    out: List[Block] = []
    for block in line:
        if block.x0 < label.x1 - 1:
            continue
        if _is_label(block):
            break
        if not _is_noise(block):
            out.append(block)
    return out


def _below(lines: Sequence[Sequence[Block]], index: int, label: Block) -> List[Block]:
    """The value blocks under `label`, on the first line below that has any.

    The column is the label's box widened by half its width on each side, and a
    block belongs to it when its CENTRE falls inside: on a row of stacked boxes
    ("CLASE | TIPO PROPIEDAD" over "URBANO | PROPIA") merely touching the window
    would pull in the neighbour's value. A value longer than the label it sits
    under has no centre in the window, so overlapping the label itself is kept as
    the second try."""
    margin = max((label.x1 - label.x0) / 2, label.h)
    for line in lines[index + 1 : index + 3]:
        usable = [b for b in line if not _is_label(b) and not _is_noise(b)]
        centred = [b for b in usable if label.x0 - margin <= b.cx <= label.x1 + margin]
        if centred:
            return centred
        overlapping = [b for b in usable if b.x1 > label.x0 and b.x0 < label.x1]
        if overlapping:
            return overlapping
    return []


def _find_label(
    lines: Sequence[Sequence[Block]], labels: Sequence[str]
) -> Tuple[float, int, Optional[Block], Optional[str]]:
    """The block that best reads as one of `labels`, and which one it was -- the
    caller needs the spelling that matched to cut it off the block's text."""
    best: Tuple[float, int, Optional[Block], Optional[str]] = (0.0, -1, None, None)
    for index, line in enumerate(lines):
        for block in line:
            for label in labels:
                score = label_score(block.text, label)
                if score > best[0]:
                    best = (score, index, block, label)
    return best


def _read_field(
    lines: Sequence[Sequence[Block]], labels: Sequence[str], kind: str
) -> Tuple[Optional[str], Optional[float], Dict[str, Any]]:
    """(value, confidence, trace) for one field. Tries the rest of the label's own
    block first (the OCR often returns "BASEIMPONIBLE:350000.00" as one block),
    then to the right of it, then under it; a candidate that does not look like the
    field is only kept when no other place gives anything at all."""
    score, index, label, matched = _find_label(lines, labels)
    if label is None or score < MIN_LABEL_SCORE:
        return None, None, {"label": None, "puntaje": round(score, 3)}

    right, below = _right_of(lines[index], label), _below(lines, index, label)
    # (where it was read, the value there, the blocks it came from -- for the
    # confidence). A place with no value at all is skipped, never fallen back to:
    # the label's own block reads as its own value if one is not careful.
    places = (
        ("mismo bloque", after_label(label.text, matched), [label]),
        ("derecha", clean_value(join_text(right)), right),
        ("abajo", clean_value(join_text(below)), below),
    )
    fallback: Optional[Tuple[str, str, List[Block]]] = None
    for where, value, blocks in places:
        if value is None:
            continue
        if _looks_like(value, kind):
            return value, min_confidence(blocks), {"label": label.text.strip(), "donde": where, "texto_ocr": value}
        if fallback is None:
            fallback = (where, value, blocks)
    if fallback is None:
        return None, None, {"label": label.text.strip(), "donde": None}
    where, value, blocks = fallback
    return value, min_confidence(blocks), {
        "label": label.text.strip(),
        "donde": where,
        "texto_ocr": value,
        "forma_inesperada": True,
    }


# "Nº 59122836" reaches this already normalized, and NFKD turns the ordinal sign
# into an "o" -- hence the NO spelling next to the others.
_RECEIPT_NUMBER_RE = re.compile(r"(?:FUR|NUMERO|NRO|NO|N)\.?\s*[:\-]?\s*(\d{4,})")
# The same thing on the raw line, where the ordinal sign is still there: only to
# take the number out of the title it is printed on.
_RECEIPT_NUMBER_AS_PRINTED = re.compile(
    r"(?:FUR|NUMERO|NRO|N)[°ºo]?\.?\s*[:\-]?\s*\d{4,}", re.IGNORECASE
)
# No word boundaries anywhere below: the OCR glues a whole printed line into one
# block and drops its spaces ("INMUEBLESIMPBI2024TOTAL"), so a boundary would
# never be there to find.
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_CI_RE = re.compile(r"C\.?\s*I\.?\s*[-:]?\s*([\d.]{5,})")
_TAXPAYER_TYPE_RE = re.compile(r"(NATURAL|JURIDICA|JURIDICO)")


def _read_lines(text_lines: Sequence[Tuple[str, Optional[float]]], reading: FurReading) -> None:
    """The values the form prints as a whole line instead of next to a label."""
    for text, confidence in text_lines:
        flat, plain = compact(text), normalize(text)
        # The number is usually printed on the title's own line, so it is taken
        # out of the type instead of being stored in both.
        number = _RECEIPT_NUMBER_RE.search(plain)
        if reading.data["receipt_type"] is None and "COMPROBANTEDEPAGO" in flat:
            without_number = _RECEIPT_NUMBER_AS_PRINTED.sub(" ", text) if number is not None else text
            reading.data["receipt_type"] = clean_value(without_number)
            reading.confidence["receipt_type"] = confidence
        if reading.data["municipality"] is None and (flat.startswith("GAM") or "GOBIERNOAUTONOMOMUNICIPAL" in flat):
            reading.data["municipality"] = clean_value(text)
            reading.confidence["municipality"] = confidence
        if reading.data["concept"] is None and ("IMPBI" in flat or plain.startswith("INMUEBLES")):
            reading.data["concept"] = clean_value(text)
            reading.confidence["concept"] = confidence
            year = _YEAR_RE.search(plain)
            if year is not None:
                reading.data["tax_year"] = year.group(0)
                reading.confidence["tax_year"] = confidence
        if reading.data["receipt_number"] is None and number is not None:
            reading.data["receipt_number"] = number.group(1)
            reading.confidence["receipt_number"] = confidence


def _read_taxpayer(lines: Sequence[Sequence[Block]], reading: FurReading, page_index: int) -> None:
    """"CONTRIBUYENTE: NATURAL CI-4482143 CRUZ COLOMI PATRICIO" -- the three
    pieces are printed as one value, so they are split here and not by position."""
    value, confidence, trace = _read_field(lines, ("CONTRIBUYENTE",), TEXT)
    reading.trace.append({"campo": "taxpayer", "foto": page_index + 1, **trace})
    if value is None:
        return
    rest = normalize(value)
    kind = _TAXPAYER_TYPE_RE.search(rest)
    if kind is not None:
        reading.data["taxpayer"]["type"] = kind.group(1)
        rest = rest.replace(kind.group(0), " ", 1)
    ci = _CI_RE.search(rest)
    if ci is not None:
        reading.data["taxpayer"]["id_number"] = ci.group(1).strip(".")
        rest = rest[: ci.start()] + " " + rest[ci.end() :]
    # Whatever is left once the type and the C.I. are out is the name.
    reading.data["taxpayer"]["name"] = clean_value(re.sub(r"\bC\.?\s*I\.?\b", " ", rest))
    for key in ("type", "id_number", "name"):
        if reading.data["taxpayer"][key] is not None:
            reading.confidence[f"taxpayer.{key}"] = confidence


def _to_number(value: Optional[str]) -> Optional[float]:
    """The printed amount as a number, for the arithmetic checks only (what is
    stored is always the text as printed). '1.234,56' and '1,234.56' both work:
    the last separator is the decimal one."""
    if not value:
        return None
    text = re.sub(r"[^\d.,]", "", value)
    if not text:
        return None
    last = max(text.rfind("."), text.rfind(","))
    if last >= 0 and len(text) - last - 1 in (1, 2):
        text = re.sub(r"[.,]", "", text[:last]) + "." + text[last + 1 :]
    else:
        text = re.sub(r"[.,]", "", text)
    try:
        return float(text)
    except ValueError:
        return None


def _check_amounts(data: Dict[str, Any], observations: List[str]) -> None:
    """The FUR does its own arithmetic on the photo, so it can be redone here: a
    reading that does not add up is a misread digit, and that is worth saying
    even when the OCR was confident about every one of them."""
    numbers = {
        key: _to_number(data.get(key))
        for key in ("assessed_tax", "exemption", "discount_10", "discount_app_5", "amount_due", "amount_paid")
    }
    due, paid = numbers["amount_due"], numbers["amount_paid"]
    if due is not None and paid is not None and abs(due - paid) > 0.5:
        observations.append(
            f"El importe a pagar ({data['amount_due']}) y el monto pagado ({data['amount_paid']}) no coinciden."
        )
    if numbers["assessed_tax"] is not None and due is not None:
        expected = numbers["assessed_tax"] - sum(
            numbers[key] or 0.0 for key in ("exemption", "discount_10", "discount_app_5")
        )
        if abs(expected - due) > 1.0:
            observations.append(
                "La liquidación no cuadra: impuesto determinado menos exención y descuentos da "
                f"{expected:,.2f} y el importe a pagar dice {data['amount_due']}."
            )


def low_confidence_fields(reading: "FurReading", confidence_threshold: float) -> List[str]:
    """The fields the OCR itself was unsure about, in the review form's keys."""
    return sorted(
        key for key, value in reading.confidence.items() if value is not None and value < confidence_threshold
    )


def missing_fields(reading: "FurReading") -> List[str]:
    """The keys the rules could not fill -- what the LLM pass is asked for."""
    missing = [key for key, _labels, _kind in FIELDS if reading.data.get(key) is None]
    missing += [key for key in LINE_FIELDS if reading.data.get(key) is None]
    if reading.data["taxpayer"]["name"] is None:
        missing.append("taxpayer")
    return missing


def parse_fur(pages: Sequence[Sequence[Block]], confidence_threshold: float) -> FurReading:
    """The OCR blocks of every photo of one receipt (page order) -> its reading.

    A receipt is one page; when there are more, each is read on its own and the
    first photo that has a value wins, so a second photo only fills gaps."""
    reading = FurReading()
    for page_index, blocks in enumerate(pages):
        lines = group_lines(list(blocks))
        text_lines = [(join_text(line), min_confidence(line)) for line in lines]
        reading.lines.extend(text for text, _confidence in text_lines if text)

        _read_lines(text_lines, reading)
        if reading.data["taxpayer"]["name"] is None:
            _read_taxpayer(lines, reading, page_index)
        for key, labels, kind in FIELDS:
            if reading.data[key] is not None:
                continue
            value, confidence, trace = _read_field(lines, labels, kind)
            reading.trace.append({"campo": key, "foto": page_index + 1, **trace})
            if value is None:
                continue
            reading.data[key] = value
            reading.confidence[key] = confidence
            if trace.get("forma_inesperada"):
                reading.observations.append(
                    f"«{trace['label']}» se leyó como «{value}», que no tiene la forma esperada: verifíquelo."
                )

    if reading.data["receipt_type"] is None and reading.data["concept"] is None:
        reading.observations.append(
            "No se reconoció el comprobante como un FUR de impuestos: revise que la foto sea la correcta."
        )
    _check_amounts(reading.data, reading.observations)

    low = low_confidence_fields(reading, confidence_threshold)
    if low:
        reading.observations.append("Campos con baja confianza de lectura: " + ", ".join(low) + ".")
    return reading
