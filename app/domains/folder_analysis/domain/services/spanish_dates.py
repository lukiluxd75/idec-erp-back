"""
Fechas escritas con letras, como las escribe un notario.

Un acta no dice "21/09/2026": dice "del día, lunes veintiun del mes de
septiembre del año dos mil veintiseis". La oficina las quiere en dd/mm/aaaa, así
que acá se pasan los números en letras a cifras -- el día, el mes por su nombre
y el año entero, que en una minuta vieja es "mil novecientos noventa y dos" y en
una de hoy "dos mil veintiseis".

Puro: solo texto (CLAUDE.md §3). El texto llega ya normalizado (mayúsculas, sin
tildes, un solo espacio) por normalize(), así que "MIÉRCOLES" es "MIERCOLES" y
"AÑO" es "ANO".
"""
import re
from typing import Optional

MONTHS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

# Las formas en que un acta escribe un número. "VEINTIUN" y "PRIMERO" están acá
# porque un día se escribe así ("veintiun del mes de", "primero de enero").
_WORDS = {
    "CERO": 0, "UN": 1, "UNO": 1, "UNA": 1, "PRIMERO": 1, "PRIMER": 1,
    "DOS": 2, "TRES": 3, "CUATRO": 4, "CINCO": 5, "SEIS": 6, "SIETE": 7,
    "OCHO": 8, "NUEVE": 9, "DIEZ": 10, "ONCE": 11, "DOCE": 12, "TRECE": 13,
    "CATORCE": 14, "QUINCE": 15, "DIECISEIS": 16, "DIECISIETE": 17,
    "DIECIOCHO": 18, "DIECINUEVE": 19, "VEINTE": 20, "VEINTIUN": 21,
    "VEINTIUNO": 21, "VEINTIUNA": 21, "VEINTIDOS": 22, "VEINTITRES": 23,
    "VEINTICUATRO": 24, "VEINTICINCO": 25, "VEINTISEIS": 26, "VEINTISIETE": 27,
    "VEINTIOCHO": 28, "VEINTINUEVE": 29, "TREINTA": 30, "CUARENTA": 40,
    "CINCUENTA": 50, "SESENTA": 60, "SETENTA": 70, "OCHENTA": 80, "NOVENTA": 90,
    "CIEN": 100, "CIENTO": 100, "DOSCIENTOS": 200, "TRESCIENTOS": 300,
    "CUATROCIENTOS": 400, "QUINIENTOS": 500, "SEISCIENTOS": 600,
    "SETECIENTOS": 700, "OCHOCIENTOS": 800, "NOVECIENTOS": 900,
}

_THOUSAND = "MIL"
_SKIPPED = {"Y", "DE", "DEL", "LOS", "LAS", "EL", "LA", "DIAS", "DIA"}

_WEEKDAYS = "LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO"


def words_to_number(text: str) -> Optional[int]:
    """El número que dicen esas palabras, o None si alguna no es un número.

    "DOS MIL VEINTISEIS" -> 2026, "MIL NOVECIENTOS NOVENTA Y DOS" -> 1992,
    "VEINTIUN" -> 21. Un texto que ya viene en cifras se devuelve tal cual.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return int(cleaned)

    total, current, seen = 0, 0, False
    for token in re.split(r"[\s,]+", cleaned):
        if not token or token in _SKIPPED:
            continue
        if token == _THOUSAND:
            # "MIL" solo vale mil; "DOS MIL" vale lo que se venía acumulando.
            current = (current or 1) * 1000
            total += current
            current, seen = 0, True
            continue
        value = _WORDS.get(token)
        if value is None:
            return None
        current += value
        seen = True
    return total + current if seen else None


def to_iso_like(day: str, month: str, year: str) -> Optional[str]:
    """dd/mm/aaaa a partir de las tres partes como vienen escritas, en letras o
    en cifras. None si alguna no se entiende: una fecha a medias es peor que
    ninguna, porque nadie la va a volver a mirar."""
    day_number = words_to_number(day)
    year_number = words_to_number(year)
    month_number = MONTHS.get((month or "").strip()) or (
        int(month) if (month or "").strip().isdigit() else None
    )
    if not day_number or not month_number or not year_number:
        return None
    if not 1 <= day_number <= 31 or not 1 <= month_number <= 12:
        return None
    # Un año de dos cifras en un acta es de este siglo ("26" -> 2026).
    if year_number < 100:
        year_number += 2000
    if not 1900 <= year_number <= 2199:
        return None
    return f"{day_number:02d}/{month_number:02d}/{year_number:04d}"


# Cómo un acta escribe su fecha. Todas dejan el día, el mes y el año en los
# grupos `day`, `month` y `year`, que es lo que to_iso_like() espera.
PATTERNS = (
    # "del día, lunes veintiun del mes de septiembre del año dos mil veintiseis"
    rf"DEL DIA[,\s]+(?:{_WEEKDAYS})?[,\s]*(?P<day>[A-Z ]+?) DEL MES DE (?P<month>[A-Z]+) DEL ANO (?P<year>[A-Z0-9 ]+?)(?=[,.;]|\s+ANTE|$)",
    # "a los veintiun días del mes de septiembre de dos mil veintiseis"
    rf"A LOS (?P<day>[A-Z0-9 ]+?) DIAS? DEL MES DE (?P<month>[A-Z]+) DE(?:L ANO)? (?P<year>[A-Z0-9 ]+?)(?=[,.;]|\s+ANTE|$)",
    # "21 de septiembre de 2026"
    r"\b(?P<day>\d{1,2}) DE (?P<month>[A-Z]+) DE(?:L ANO)? (?P<year>\d{4})\b",
)
