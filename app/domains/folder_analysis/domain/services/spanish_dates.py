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


# Cifras que el OCR devuelve por letras dentro de una palabra impresa: el mes de
# una minuta fotografiada sale "AGOST0" o "5EPTIEMBRE". Se aplica solo al nombre
# del mes -- nunca al día ni al año, que son cifras de verdad y una confusión ahí
# tiene que quedar a la vista del arquitecto.
_LOOKALIKE_LETTERS = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B"})


def month_number(month: str) -> Optional[int]:
    """El número del mes por su nombre, en cifras o con la letra que el OCR
    cambió por una cifra."""
    name = (month or "").strip()
    if not name:
        return None
    if name.isdigit():
        return int(name)
    return MONTHS.get(name) or MONTHS.get(name.translate(_LOOKALIKE_LETTERS))


def to_iso_like(day: str, month: str, year: str) -> Optional[str]:
    """dd/mm/aaaa a partir de las tres partes como vienen escritas, en letras o
    en cifras. None si alguna no se entiende: una fecha a medias es peor que
    ninguna, porque nadie la va a volver a mirar."""
    day_number = words_to_number(day)
    year_number = words_to_number(year)
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
    return f"{day_number:02d}/{month_number_value:02d}/{year_number:04d}"


# El año va detrás de "de", "del" o "del año": una minuta cierra con "26 de
# Agosto del 2014" tan seguido como con "de 2014", y sin la forma "del" esa
# fecha no se leía.
_OF_THE_YEAR = r"DE(?:L(?: ANO)?)?"

# Lo que separa las palabras de una fecha en una hoja fotografiada. No es solo el
# espacio: el OCR mete las rayas del renglón y los puntos de la línea de puntos
# entre medio, y una fecha manuscrita sobre el renglón sale "26 de/Agosto del
# 2014". Sin esto la fecha de cierre de la minuta no se leía.
_SEP = r"[\s/.,·-]+"

# La fecha en cifras, con el día, el mes y el año en los grupos que to_iso_like()
# espera. El mes admite cifras porque el OCR cambia letras por números dentro de
# la palabra ("AGOST0"); month_number() las devuelve a su letra.
_FIGURES = (
    rf"\b(?P<day>\d{{1,2}}){_SEP}DE{_SEP}(?P<month>[A-Z0-9]+){_SEP}{_OF_THE_YEAR}{_SEP}(?P<year>\d{{4}})\b"
)

# Cómo un acta escribe su fecha. Todas dejan el día, el mes y el año en los
# grupos `day`, `month` y `year`, que es lo que to_iso_like() espera.
PATTERNS = (
    # "del día, lunes veintiun del mes de septiembre del año dos mil veintiseis"
    rf"DEL DIA[,\s]+(?:{_WEEKDAYS})?[,\s]*(?P<day>[A-Z ]+?) DEL MES DE (?P<month>[A-Z]+) DEL ANO (?P<year>[A-Z0-9 ]+?)(?=[,.;]|\s+ANTE|$)",
    # "a los veintiun días del mes de septiembre de dos mil veintiseis"
    rf"A LOS (?P<day>[A-Z0-9 ]+?) DIAS? DEL MES DE (?P<month>[A-Z]+) {_OF_THE_YEAR} (?P<year>[A-Z0-9 ]+?)(?=[,.;]|\s+ANTE|$)",
    # La fecha del acto antes que ninguna otra. Una minuta cita las fechas de los
    # documentos que la anteceden ("sentencia de fecha 08 de Agosto de 1996",
    # "según documento de fecha 29 de Agosto del 2007") y esas vienen primero en
    # la hoja; la suya propia cierra el documento junto a la ciudad y no lleva
    # "fecha" delante. Sin este orden se guardaba la del antecedente.
    rf"(?<!FECHA ){_FIGURES}",
    # Último recurso, para la hoja cuya única fecha va presentada como tal
    # ("declaración jurada de fecha 12 de marzo de 2025").
    _FIGURES,
)
