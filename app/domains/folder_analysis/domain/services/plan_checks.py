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

_NEXT = r"(?=\s+(?:SUB\s*-?\s*DISTRITO|DISTRITO|MANZANA|LOTE|VIA|ZONA)\s*[:;.]|\s+PROCESAMIENTO|\s*$)"
_SEP = r"\s*[:;.]\s*"
_FIELDS = {
    "zone": re.compile(r"\bZONA" + _SEP + r"(.+?)" + _NEXT),
    "subdistrict": re.compile(r"\bSUB\s*-?\s*DISTRITO" + _SEP + r"(\d+)"),
    "district": re.compile(r"(?<!SUB )(?<!SUB)(?<!SUB-)\bDISTRITO" + _SEP + r"(\d+)"),
    "block": re.compile(r"\bMANZANA" + _SEP + r"(\d+)"),
    "lot": re.compile(r"\bLOTE" + _SEP + r"(\d+)"),
    "street": re.compile(r"\bVIA" + _SEP + r"(.+?)" + _NEXT),
}


def read_location_block(text: str) -> Dict[str, Optional[str]]:
    """What the box says, by field. A line the OCR did not give is None."""
    prose = normalize(text or "")
    found: Dict[str, Optional[str]] = {}
    for key, pattern in _FIELDS.items():
        match = pattern.search(prose)
        found[key] = match.group(1).strip(" .") if match else None
    return found


def _number(value: Any) -> Optional[int]:
    digits = re.sub(r"\D", "", str(value or ""))
    return int(digits) if digits else None


def _same_number(plan: Any, gis: Any) -> bool:
    return _number(plan) is not None and _number(plan) == _number(gis)


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
        ("block", "Manzana", _same_number),
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
