"""
The "ubicación" box of a poseedores plano -- ZONA, DISTRITO, SUB DISTRITO,
MANZANA, LOTE, VIA, printed under the croquis -- checked against what the GIS says
about the predio its code points at.

The code catastral finds the predio, but nothing guarantees that the plano was
drawn for it: a code misread by the OCR, or mistyped by the draughtsman, lands on
another lot. The box repeats the location in words and numbers, so every line that
agrees is one more reason to trust the match, and a line that does not is the one
to look at before the carpeta is closed.

Pure: it only touches the text and the facts it is given (CLAUDE.md §3).
"""
import re
from typing import Any, Dict, List, Optional

from app.domains.folder_analysis.domain.services.text import normalize

OK = "ok"
DIFFERS = "differs"
MISSING = "missing"

# The OCR reads this box badly: colons go missing ("SUB DISTRITO33"), a word is
# misspelled ("MANZANO 432") and the zone runs into the next label
# ("KHARA KHARAARRUMANI"). So the separator is optional, the numbers must follow
# the label directly (which keeps "LOTE N: 5" of the drawing out of it) and a
# value ends where the next label starts.
_NEXT = r"(?=\s+(?:SUB\s*-?\s*DISTRITO|DISTRITO|MANZAN[AO]|LOTE|VIA|ZONA|ARQUITECTO|SELLO)\b|\s+PROCESAMIENTO|\s*$)"
_SEP = r"[\s:;.]*"
_FIELDS = {
    "zone": re.compile(r"\bZONA" + _SEP + r"(.+?)" + _NEXT),
    "subdistrict": re.compile(r"\bSUB\s*-?\s*DISTRITO" + _SEP + r"(\d+)"),
    "district": re.compile(r"(?<!SUB )(?<!SUB)(?<!SUB-)\bDISTRITO" + _SEP + r"(\d+)"),
    "block": re.compile(r"\bMANZAN[AO]" + _SEP + r"([A-Z]?\d{1,4})"),
    # Three digits, as the box pads them ("002"): a smudged "0." is not a lote.
    "lot": re.compile(r"\bLOTE" + _SEP + r"(\d{3})(?!\d)"),
    "street": re.compile(r"\bVIA" + _SEP + r"(.+?)" + _NEXT),
}


# The second format of the plano heads the box with the zone ("DATOS DE UBICACION :
# PUKARA GRANDE NORTE") and then lists ZONA, DISTRITO... with the values in other
# blocks, so the zone is not after its own label. A zone "found" after ZONA that is
# really the next label (MANZANA : 494...) is not a zone.
_ZONE_HEADING = re.compile(r"\bDATOS\s*DE\s*UBICACION\s*[:;.]\s*(.+?)" + _NEXT)
_LABEL_START = re.compile(r"^(?:SUB\s*-?\s*DISTRITO|DISTRITO|MANZAN[AO]|LOTE|VIA)\b")


_NOT_A_STREET = ("ARQUITECTO", "PROCESAMIENTO", "FIRMA", "SELLO", "REGISTRO", "ESCALA")


def read_location_block(text: str) -> Dict[str, Optional[str]]:
    """What the box says, by field. A line the OCR did not give is None."""
    prose = normalize(text or "")
    found: Dict[str, Optional[str]] = {}
    for key, pattern in _FIELDS.items():
        # The box is the last thing on the sheet that says these words: the first
        # "ZONA" or "LOTE" can belong to the drawing or to its coordinates table.
        matches = list(pattern.finditer(prose))
        found[key] = matches[-1].group(1).strip(" .") if matches else None
    if found["zone"] and _LABEL_START.match(found["zone"]):
        found["zone"] = None
    if not found["zone"]:
        heading = list(_ZONE_HEADING.finditer(prose))
        found["zone"] = heading[-1].group(1).strip(" .") if heading else None
    # A VIA left blank is followed by the next heading of the sheet, not by a street.
    if found["street"] and found["street"].startswith(_NOT_A_STREET):
        found["street"] = None
    return found


def _number(value: Any) -> Optional[int]:
    digits = re.sub(r"\D", "", str(value or ""))
    return int(digits) if digits else None


def _same_number(plan: Any, gis: Any) -> bool:
    return _number(plan) is not None and _number(plan) == _number(gis)


def _same_code(plan: Any, gis: Any) -> bool:
    """A manzana is a code ("432", "B37"): equal as written, letter included."""
    a, b = _letters(plan), _letters(gis)
    return bool(a) and a == b


def _letters(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize(str(value or "")))


def _same_words(plan: Any, gis: Any) -> bool:
    a, b = _letters(plan), _letters(gis)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def cross_check(location: Dict[str, Optional[str]], gis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One line per field of the box: what the plano says, what the GIS says and
    whether they agree. `gis` carries zone, district, subdistrict, block and lot."""
    spec = [
        ("zone", "Zona", _same_words),
        ("district", "Distrito", _same_number),
        ("subdistrict", "Sub distrito", _same_number),
        ("block", "Manzana", _same_code),
        ("lot", "Lote", _same_number),
    ]
    checks: List[Dict[str, Any]] = []
    for key, label, same in spec:
        plan_value, gis_value = location.get(key), gis.get(key)
        if plan_value in (None, ""):
            status = MISSING
        else:
            status = OK if same(plan_value, gis_value) else DIFFERS
        checks.append(
            {
                "key": key,
                "label": label,
                "plan": plan_value,
                "gis": None if gis_value in (None, "") else str(gis_value),
                "status": status,
            }
        )
    return checks
