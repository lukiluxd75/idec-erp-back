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
from datetime import date
from typing import Optional

from app.domains.folder_analysis.domain.services.text import normalize, similar

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

# Las formas en que un acta escribe un número.
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

# Cómo se escribe de verdad un número en estas hojas, además de como lo manda la ortografía.
_VARIANTS = {
    "VENTIUN": 21, "VENTIUNO": 21, "VENTIUNA": 21, "VENTIDOS": 22, "VENTITRES": 23,
    "VENTICUATRO": 24, "VENTICINCO": 25, "VENTISEIS": 26, "VENTISIETE": 27,
    "VENTIOCHO": 28, "VENTINUEVE": 29, "VENTE": 20,
    "DIECISEIS": 16, "DIEZISEIS": 16, "DIESISEIS": 16, "DIESISIETE": 17,
    "DIESIOCHO": 18, "DIESINUEVE": 19,
    "PRIMERA": 1, "SEGUNDO": 2, "TERCERO": 3,
}

_THOUSAND = "MIL"
_SKIPPED = {"Y", "DE", "DEL", "LOS", "LAS", "EL", "LA", "DIAS", "DIA"}

_WEEKDAYS = "LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO"


def leading_number(text: str) -> Optional[int]:
    """El número con el que ARRANCA ese texto, cortando donde deja de serlo.

    Es lo que deja capturar con holgura y entender igual: un acta no termina su
    fecha en el mismo lado en cada hoja ("del ano dos mil veintiseis, ANTE MI",
    "de dos mil veintiseis y en presencia de"), y pedirle al patrón que adivine
    dónde corta era lo que hacía que una redacción nueva no se leyera. Acá se
    toman las palabras que son número y se para en la primera que no lo es.

    None cuando ni la primera palabra es un número: ahí no hay nada que leer.
    """
    total, current, seen = 0, 0, False
    for token in re.split(r"[\s,]+", (text or "").strip()):
        if not token or token in _SKIPPED:
            continue
        # Una cifra ya es el número entero: "21", "2026".
        if token.isdigit():
            return int(token) if not seen else total + current
        if token == _THOUSAND:
            current = (current or 1) * 1000
            total += current
            current, seen = 0, True
            continue
        value = _number_word(token)
        if value is None:
            break
        current += value
        seen = True
    return total + current if seen else None


def _number_word(token: str) -> Optional[int]:
    """El número que dice esa palabra, aguantando cómo salió de la foto.

    Primero tal cual, después las formas que se escriben de verdad ("ventiuno"),
    y recién al final por parecido, que es lo que salva a la palabra con una
    letra cambiada ("VEINTIUN" leído "VElNTIUN"). El parecido se exige alto: una
    palabra que no es un número tiene que quedar afuera, porque una fecha
    inventada no la vuelve a mirar nadie.
    """
    exact = _WORDS.get(token)
    if exact is not None:
        return exact
    variant = _VARIANTS.get(token)
    if variant is not None:
        return variant
    if len(token) < 4:
        # Dos o tres letras se parecen a cualquier cosa.
        return None
    best, score = None, MIN_WORD_RATIO
    for word, value in _WORDS.items():
        ratio = similar(token, word)
        if ratio >= score:
            best, score = value, ratio
    return best


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
        value = _WORDS.get(token) or _VARIANTS.get(token)
        if value is None:
            return None
        current += value
        seen = True
    return total + current if seen else None


_LOOKALIKE_LETTERS = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B"})

# Cuánto tiene que parecerse una palabra a la que debería ser para darla por esa.
MIN_WORD_RATIO = 0.86
MIN_MONTH_RATIO = 0.80


def month_number(month: str) -> Optional[int]:
    """El número del mes por su nombre, en cifras o con la letra que el OCR
    cambió por una cifra."""
    name = (month or "").strip()
    if not name:
        return None
    if name.isdigit():
        return int(name)
    exact = MONTHS.get(name) or MONTHS.get(name.translate(_LOOKALIKE_LETTERS))
    if exact is not None:
        return exact
    # Y por parecido, para el mes al que la foto le cambió una letra ("SEPTlEMBRE", "NOVLEMBRE").
    best, score = None, MIN_MONTH_RATIO
    for month, number in MONTHS.items():
        ratio = similar(name, month)
        if ratio >= score:
            best, score = number, ratio
    return best


def to_iso_like(day: str, month: str, year: str) -> Optional[str]:
    """dd/mm/aaaa a partir de las tres partes como vienen escritas, en letras o
    en cifras. None si alguna no se entiende: una fecha a medias es peor que
    ninguna, porque nadie la va a volver a mirar."""
    day_number = leading_number(day)
    year_number = leading_number(year)
    month_number_value = month_number(month)
    if not day_number or not month_number_value or not year_number:
        return None
    if not 1 <= day_number <= 31 or not 1 <= month_number_value <= 12:
        return None
    # Un año de dos cifras en un acta es de este siglo ("26" -> 2026).
    if year_number < 100:
        year_number += 2000
    if not 1900 <= year_number <= 2199:
        return None
    try:
        date(year_number, month_number_value, day_number)
    except ValueError:
        return None
    return f"{day_number:02d}/{month_number_value:02d}/{year_number:04d}"


_OF_THE_YEAR = r"DE(?:L(?:\s+ANO)?)?"

# Lo que separa las palabras de una fecha en una hoja fotografiada.
_SEP = r"[\s/.,·-]+"

# La fecha en cifras, con el día, el mes y el año en los grupos que to_iso_like() espera.
_FIGURES = (
    rf"\b(?P<day>\d{{1,2}}){_SEP}DE{_SEP}(?P<month>[A-Z0-9]+){_SEP}{_OF_THE_YEAR}{_SEP}(?P<year>\d{{4}})\b"
)

# El día, en letras o en cifras.
_DAY = r"(?P<day>\d{1,2}|[A-Z]+(?:\s+Y\s+[A-Z]+)?)"

# Lo que separa dos palabras de una fecha en una hoja FOTOGRAFIADA.
_GAP = r"[\s/.,:;·_-]+"

# El año, en letras o en cifras.
_YEAR = r"(?P<year>\d{4}|[A-Z]+(?:\s+[A-Z]+){0,4})"

# El mes por su nombre.
_MONTH = r"(?P<month>[A-Z0-9]+)"

# "del mes de septiembre" y "de septiembre" son la misma cosa, y las dos se escriben.
_OF_THE_MONTH = rf"(?:DEL{_GAP}MES{_GAP})?DE"

# La fecha escrita entera con palabras y sin nada que la anuncie: "veinte y uno de septiembre de dos mil veintiseis".
_LOOSE = rf"\b{_DAY}{_GAP}{_OF_THE_MONTH}{_GAP}{_MONTH}{_GAP}{_OF_THE_YEAR}{_GAP}{_YEAR}"

# La fecha en cifras con barras, puntos o guiones: "21/09/2026", "21-09-2026".
_SLASHED = r"(?P<day>\d{1,2})\s*[/.-]\s*(?P<month>\d{1,2})\s*[/.-]\s*(?P<year>\d{4})\b"

# La misma, pero detrás de la palabra que la presenta.
_LABELLED_SLASHED = rf"\bFECHAS?\W{{0,6}}{_SLASHED}"

# Y suelta, que es el último recurso de todos.
_BARE_SLASHED = rf"(?<!\d\s)\b{_SLASHED}"

# Cómo un acta escribe su fecha.
PATTERNS = (
    rf"\b(?:DEL\s+|EL\s+|AL\s+)?DIA\b{_GAP}(?:(?:{_WEEKDAYS}){_GAP})?{_DAY}{_GAP}{_OF_THE_MONTH}{_GAP}{_MONTH}{_GAP}{_OF_THE_YEAR}{_GAP}{_YEAR}",
    rf"\b(?:{_WEEKDAYS})\b{_GAP}{_DAY}{_GAP}{_OF_THE_MONTH}{_GAP}{_MONTH}{_GAP}{_OF_THE_YEAR}{_GAP}{_YEAR}",
    # "a los veintiun días del mes de septiembre de dos mil veintiseis", "a los 21 días de septiembre del año 2026"
    rf"\bA\s+LOS{_GAP}{_DAY}{_GAP}DIAS?{_GAP}{_OF_THE_MONTH}{_GAP}{_MONTH}{_GAP}{_OF_THE_YEAR}{_GAP}{_YEAR}",
    # La fecha en cifras detrás de su palabra: "Fecha: 21/09/2026".
    _LABELLED_SLASHED,
    # La fecha del acto antes que ninguna otra.
    rf"(?<!FECHA ){_FIGURES}",
    _FIGURES,
    _LOOSE,
    _BARE_SLASHED,
)

# Una fecha escrita en cifras y separada por barras, guiones o puntos.
_SHORT_SLASHED = re.compile(r"\b(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2,4})\b")

# La misma fecha al revés, que es como la escribe un modelo que se olvidó del formato que se le pidió ("2026-09-21").
_ISO = re.compile(r"\b(\d{4})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})\b")


def any_date(text: str) -> Optional[str]:
    """Una fecha escrita de cualquiera de estas formas, en dd/mm/aaaa.

    Existe para lo que contesta el modelo de visión: se le pide la fecha en
    dd/mm/aaaa y la devuelve así casi siempre, pero también la devuelve como la
    leyó de la hoja ("21 de septiembre de 2026") o en el orden del año primero
    ("2026-09-21"). La oficina la quiere en una sola forma, así que se la pasa
    por acá antes de guardarla.

    None cuando no se entiende, que es lo que corresponde: una fecha a medias o
    dada vuelta es peor que un campo vacío, porque nadie la vuelve a mirar.
    """
    prose = (text or "").strip()
    if not prose:
        return None

    iso = _ISO.search(prose)
    if iso is not None:
        return to_iso_like(iso.group(3), iso.group(2), iso.group(1))

    slashed = _SHORT_SLASHED.search(prose)
    if slashed is not None:
        # Siempre día/mes/año: es lo que se le pidió al modelo y lo que escribe la oficina.
        return to_iso_like(slashed.group(1), slashed.group(2), slashed.group(3))

    upper = normalize(prose)
    for pattern in PATTERNS:
        match = re.search(pattern, upper)
        if match is None:
            continue
        parts = match.groupdict()
        value = to_iso_like(parts.get("day", ""), parts.get("month", ""), parts.get("year", ""))
        if value:
            return value
    return None
