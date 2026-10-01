"""
The code catastral, as the plano prints it and as the GIS stores it.

The plano prints 19 digits in groups ("00-33-432-012-0-00-000-000"); the GIS layer
of predios keys the same parcel by 17 digits with no group separators: the first
two digits of the printed code are not part of it, so what the layer calls CodCat
is subdistrito (2) + manzana (3) + predio (3) + the nine digits of unit/block.

A code that points at a unit inside a building (a P.H. piso or local) is brought
back to its predio before looking it up: the map draws lots, not apartments.

Pure (CLAUDE.md §3).
"""
import re
from typing import Optional

from app.domains.folder_analysis.domain.exceptions import InvalidDocumentRequestException

GIS_CODE_LENGTH = 17
PRINTED_CODE_LENGTH = 19


def to_gis_code(raw: Optional[str]) -> str:
    """The key the GIS knows the predio by, from the code as typed or printed."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == PRINTED_CODE_LENGTH:
        digits = digits[2:]
    if len(digits) != GIS_CODE_LENGTH:
        raise InvalidDocumentRequestException(
            "El código catastral debe tener 19 dígitos (como figura en el plano) o 17 (como lo guarda el GIS)."
        )
    # Unit digit in the first position after the predio: it is a piso/local of the
    # lot, and the lot is what the map has.
    if digits[8] != "0":
        digits = digits[:9] + "0" * 8
    return digits


def printed(gis_code: str) -> str:
    """The same code as the plano prints it (19 digits, grouped)."""
    d = "00" + gis_code
    return f"{d[0:2]}-{d[2:4]}-{d[4:7]}-{d[7:10]}-{d[10]}-{d[11:13]}-{d[13:16]}-{d[16:19]}"
