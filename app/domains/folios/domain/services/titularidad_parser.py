"""
Column A) TITULARIDAD SOBRE EL DOMINIO -> structured asientos.

Column A is SINAREP-generated text, one fact per line, with a stable shape per
asiento, e.g. (real folio, filler removed):

    Asiento Numero: 0            <- antecedent: who sold
    Vendedor(es):
    MENESES RODRIGUEZ PATRICIA
    Asiento Numero: 1
    CRUZ COLOMI PATRICIO         [1/1 in the PROPORCIÓN column]
    sol. c/CI 4482143 CBA
    Compra Venta
    Escrit. Priv. de fecha 12/10/1992
    Not. Pub. FRANCISCO VILLARROEL
    JUEZ DE MINIMA CUANTIA
    Present.- No. 8904 de 27/10/2014.- Hrs.11:24:56
    [GPF]-[GPF]-[GPF]            <- registrar initials
    Ultimo Asiento Nro. 1

so a line classifier + a small state machine reads it without an LLM. What it
cannot classify is kept verbatim in `texto` (always present) so nothing is lost;
the optional LLM pass (ProcessFolioUseCase) only fills gaps.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.domains.folios.domain.services.text import compact, is_filler, normalize, similar, strip_filler


@dataclass(frozen=True)
class ColumnLine:
    """One text line of column A (already filler-stripped), with the proportion
    printed on its row in the PROPORCIÓN column, if any."""

    text: str
    confidence: float
    page: int
    proportion: Optional[str] = None


_LOOKALIKE_DIGITS = str.maketrans({"L": "1", "I": "1", "O": "0", "S": "5", "B": "8", "Z": "2"})
_ASIENTO_RE = re.compile(r"^A?S?IENTO(?:NUMERO|NRO|N)?([0-9LIOSBZ]{1,3})$")
_ULTIMO_RE = re.compile(r"ULTIMOASIENTO(?:NRO|NUMERO|N)?([0-9LIOSBZ]{1,3})")
_CI_RE = re.compile(r"(?:C\s*/\s*\.?\s*)?C\s*\.?\s*I\s*\.?\s*:?\s*(\d[\d\s]{3,11}\d)\s*-?\s*([A-Z]{2,3})?\b")
_DATE_RE = re.compile(r"(\d{1,2})\s*/\s*([\dLIO]{1,2})\s*/\s*(\d{4})")
# Low-resolution photos lose the 'CI' ('ol..c/14482143'): 'c/' + a digit run,
# where a leading 1 is usually the 'I' misread.
_CI_LOOSE_RE = re.compile(r"C\s*/\s*\.?\s*[I1L]?\s*\.?\s*(\d{5,10})\s*([A-Z]{2,3})?")
_SECTION_WORDS = ("VENDEDOR", "COMPRADOR", "DONANTE", "DONATARIO", "HEREDERO", "CAUSANTE",
                  "TRANSFERENTE", "ADQUIRENTE", "CEDENTE", "CESIONARIO")
_NATIONALITY_RE = re.compile(r"^(NACIONALIDAD\b|BOLIVIAN|[A-Z]{4,}[OA]\s*\(\s*[AO]\s*\)$)")
_CIVIL = {"SOL": "soltero(a)", "CAS": "casado(a)", "VIU": "viudo(a)", "DIV": "divorciado(a)"}
_DOC_PREFIXES = ("ESCRIT", "TESTIM", "MINUTA", "RESOL", "AUTO", "SENTEN", "DOCUMENTO", "FORMULARIO",
                 "CONTRATO", "PROTOCOLO", "INSTRUMENTO", "TITULO", "DECLARATORIA JUD")
_AUTHORITY_PREFIXES = ("NOT", "JUEZ", "JUZGADO", "TRIBUNAL", "NOTARI", "OFICIAL", "REGISTRADOR", "DIRECTOR", "INRA")
_KNOWN_ACTS = (
    "COMPRA VENTA", "COMPRAVENTA", "DONACION", "SUCESION", "DECLARATORIA DE HEREDEROS", "HEREDEROS",
    "PERMUTA", "ADJUDICACION", "DIVISION Y PARTICION", "DIVISION", "USUCAPION", "DACION EN PAGO",
    "ANTICIPO DE LEGITIMA", "TRANSFERENCIA", "APORTE DE CAPITAL", "FUSION", "CESION", "REMATE",
    "DOTACION", "TITULACION", "REGULARIZACION", "RECTIFICACION",
)
_NOT_A_NAME = _DOC_PREFIXES + _AUTHORITY_PREFIXES + ("ASIENTO", "PRESENT", "ULTIMO", "VENDEDOR", "COMPRADOR",
                                                     "ANTECEDENTE", "PROPOR")


def _digits(token: str) -> Optional[int]:
    try:
        return int(token.upper().translate(_LOOKALIKE_DIGITS))
    except ValueError:
        return None


def _date(text: str) -> Optional[str]:
    m = _DATE_RE.search(normalize(text))
    if not m:
        return None
    day, month, year = m.group(1), m.group(2).translate(_LOOKALIKE_DIGITS), m.group(3)
    return f"{int(day):02d}/{int(month):02d}/{year}"


def _asiento_number(line: str) -> Optional[int]:
    c = compact(line)
    m = _ASIENTO_RE.match(c)
    if m:
        return _digits(m.group(1))
    # OCR noise in "ASIENTONUMERO": a wrong letter ('ASIENTONUNERO0'), or a
    # missing one when the column crop clips the left edge ('SIENTOMUMERO0'),
    # which shifts everything and so rules out a fixed offset. The cut that
    # matches the word best wins; the longest one wins ties, so the word's own
    # final 'O' is not taken for a zero when the digit was dropped.
    cuts = [cut for cut in range(12, 17) if cut <= len(c)]
    score, cut = max(((similar(c[:cut], "ASIENTONUMERO"), cut) for cut in cuts), default=(0.0, 0))
    if score >= 0.84:
        return _digits(c[cut : cut + 3])
    return None


def _is_act(norm: str) -> bool:
    flat = norm.replace(".", " ").replace("-", " ")
    flat = re.sub(r"\s+", " ", flat)
    if any(flat.startswith(a) or a in flat for a in _KNOWN_ACTS):
        return True
    # One or two wrong letters ('CompraVente'): fuzzy on the compacted start.
    c = compact(norm)
    return any(len(a) >= 8 and similar(c[: len(compact(a))], compact(a)) >= 0.85 for a in _KNOWN_ACTS)


def _section_role(norm: str) -> Optional[str]:
    """'Vendedor(es):' and its OCR variants ('Vendedorles', no colon) -> 'vendedor'."""
    c = compact(norm)
    if len(c) > 16:
        return None
    for word in _SECTION_WORDS:
        if c.startswith(word) or (len(c) >= len(word) and similar(c[: len(word)], word) >= 0.85):
            return word.lower()
    return None


def _civil_status(norm: str) -> Optional[str]:
    first = norm.split(" ")[0].replace("0", "O").replace("1", "L")
    return _CIVIL.get(first[:3])


def _parse_ci(norm: str) -> Optional[Dict[str, Optional[str]]]:
    # Works on glued OCR too ('SO1.C/CI4482143CBA'); the civil-status token's
    # digit lookalikes are handled separately in _civil_status.
    m = _CI_RE.search(norm) or _CI_LOOSE_RE.search(norm)
    if not m:
        return None
    return {"ci": re.sub(r"\s+", "", m.group(1)), "expedido": m.group(2)}


# The married-name particle, printed in lower case at the end of an otherwise
# all-caps typed name: "RONDAL BORDA MARGARITA de", "SILES vda. de".
_NAME_PARTICLE = re.compile(r"(?:\s+V(?:IU)?D[AO]?\.?)?\s+DE(?:\s+LA)?\.?$", re.IGNORECASE)


def _is_name(norm: str, raw: str) -> bool:
    if any(ch.isdigit() for ch in norm) or ":" in raw:
        return False
    if any(norm.startswith(p) for p in _NOT_A_NAME) or _is_act(norm):
        return False
    letters = re.sub(r"[^A-Z]", "", norm)
    if len(letters) < 6:
        return False
    # Typed names are all caps; lower-case letters mean a descriptive line. The
    # married-name particle at the end is the one exception -- without it every
    # "NOMBRE APELLIDO de" on the form was dropped.
    return sum(1 for ch in _NAME_PARTICLE.sub("", raw.strip()) if ch.islower()) <= 1


def _presentation(norm: str) -> Dict[str, Optional[str]]:
    number = re.search(r"N\s*[O0°º]?\s*\.?\s*-?\s*(\d{2,8})", norm.split("DE")[0] if "DE" in norm else norm)
    hour = re.search(r"HRS?\s*\.?\s*:?\s*(\d{1,2})\s*[:.]?\s*(\d{2})\s*[:.]?\s*(\d{2})", norm)
    return {
        "numero": number.group(1) if number else None,
        "fecha": _date(norm),
        "hora": f"{int(hour.group(1)):02d}:{hour.group(2)}:{hour.group(3)}" if hour else None,
    }


def _new_asiento(number: Optional[int]) -> Dict[str, Any]:
    return {
        "numero": number,
        "personas": [],
        "acto": None,
        "documento": None,
        "autoridad": None,
        "presentacion": None,
        "texto": [],
        "_conf": [],
        "_stage": "people",  # people -> act -> document -> authority -> done
        "_role": "titular",
    }


def parse_titularidad(lines: Sequence[ColumnLine], trace: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """{'asientos': [...], 'ultimo_asiento': int|None, 'antecedente_dominial': str|None,
    'lineas_sin_asiento': [...]} -- asientos in reading order across pages.

    `trace` (fill log): gets one entry per line with how it was classified and
    the asiento it ended up in."""
    asientos: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    last_declared: Optional[int] = None
    antecedent: Optional[str] = None
    orphans: List[str] = []

    for line in lines:
        def note(kind: str) -> None:
            if trace is not None:
                trace.append({
                    "foto": line.page + 1,
                    "texto_ocr": line.text,
                    "confianza": round(line.confidence, 4),
                    "proporcion": line.proportion,
                    "clasificacion": kind,
                    "_asiento": current,
                })

        raw = strip_filler(line.text)
        if not raw or is_filler(raw):
            note("relleno")
            continue
        norm = normalize(raw)
        c = compact(raw)

        m = _ULTIMO_RE.search(c)
        if m:
            last_declared = _digits(m.group(1))
            note("ultimo_asiento")
            continue
        if "ANTECEDENTE" in c or "DOMINIAL" in c:
            antecedent = raw.split(":", 1)[1].strip() if ":" in raw else antecedent
            note("antecedente_dominial")
            continue
        number = _asiento_number(raw)
        if number is not None or c.startswith("ASIENTO"):
            current = _new_asiento(number)
            asientos.append(current)
            current["texto"].append(raw)
            current["_conf"].append(line.confidence)
            note("inicio_asiento")
            continue
        if current is None:
            orphans.append(raw)
            note("sin_asiento")
            continue

        current["texto"].append(raw)
        current["_conf"].append(line.confidence)
        stage = current["_stage"]

        # Section headings inside an asiento: 'Vendedor(es):', 'Comprador(es):'...
        role = _section_role(norm)
        if role is None and re.fullmatch(r"[A-Z]+(\(?ES\)?|\(?S\)?)?\s*:", norm.replace(" ", "")):
            word = norm.split("(")[0].split(":")[0].strip().lower()
            role = word[:-2] if word.endswith("es") and word[:-2].endswith("or") else word
        if role is not None:
            current["_role"] = role
            current["_stage"] = "people"
            note(f"seccion:{role}")
            continue

        if c.startswith("PRESENT"):
            current["presentacion"] = _presentation(norm)
            current["_stage"] = "done"
            note("presentacion")
            continue

        ci = _parse_ci(norm)
        if ci and current["personas"] and stage == "people":
            person = current["personas"][-1]
            person.update(ci)
            person["estado_civil"] = person.get("estado_civil") or _civil_status(norm)
            birth = re.search(r"NAC\.?\s*(\d{1,2}/\d{1,2}/\d{4})", norm)
            if birth:
                person["fecha_nacimiento"] = birth.group(1)
            note("ci_de_persona")
            continue

        if current["personas"] and stage == "people" and _NATIONALITY_RE.match(norm):
            current["personas"][-1]["nacionalidad"] = raw
            note("nacionalidad")
            continue

        if stage in ("people", "act") and any(norm.startswith(p) for p in _DOC_PREFIXES):
            current["documento"] = {"descripcion": raw, "fecha": _date(raw)}
            current["_stage"] = "authority"
            note("documento")
            continue

        if stage == "people" and _is_name(norm, raw):
            current["personas"].append({
                "nombre": raw.rstrip(".").strip(),
                "rol": current["_role"],
                "estado_civil": None,
                "ci": None,
                "expedido": None,
                "proporcion": line.proportion,
            })
            note(f"persona:{current['_role']}")
            continue

        # An act never carries digits (those lines are CI / dates the rules
        # could not read -- they stay in `texto`).
        if (
            stage in ("people", "act")
            and current["acto"] is None
            and (_is_act(norm) or (current["personas"] and not any(ch.isdigit() for ch in norm)))
        ):
            current["acto"] = raw
            current["_stage"] = "act"
            note("acto")
            continue

        if stage == "authority":
            raw = re.sub(r"(?<=[a-z])[.-]\s*(?=[A-Z])", ". ", raw)  # 'Not- Pub.FRANCISCO' -> 'Not. Pub. FRANCISCO'
            current["autoridad"] = f"{current['autoridad']} - {raw}" if current["autoridad"] else raw
            note("autoridad")
            continue
        # Anything else stays only in `texto`.
        note(f"sin_clasificar (etapa: {stage})")

    _infer_missing_numbers(asientos, last_declared)
    for entry in trace or []:
        owner = entry.pop("_asiento", None)
        entry["asiento"] = owner["numero"] if owner is not None else None
    for a in asientos:
        conf = a.pop("_conf")
        a.pop("_stage")
        a.pop("_role")
        a["texto"] = "\n".join(a["texto"])
        a["confianza"] = round(min(conf), 4) if conf else None

    return {
        "asientos": asientos,
        "ultimo_asiento": last_declared,
        "antecedente_dominial": antecedent,
        "lineas_sin_asiento": orphans,
    }


def _infer_missing_numbers(asientos: List[Dict[str, Any]], last_declared: Optional[int]) -> None:
    """OCR sometimes drops the digit entirely ('Asiento Numero:' -- seen on
    low-resolution photos). Asientos are numbered consecutively, so: take it
    from a neighbour (repeat until nothing changes); if none was read at all,
    count backwards from 'Ultimo Asiento Nro. N', else forward from 0 (column
    A starts with the antecedent, asiento 0). Always flagged as inferred."""
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(asientos):
            if a["numero"] is not None:
                continue
            prev_n = asientos[i - 1]["numero"] if i > 0 else None
            next_n = asientos[i + 1]["numero"] if i + 1 < len(asientos) else None
            if prev_n is not None:
                a["numero"] = prev_n + 1
            elif next_n is not None and next_n > 0:
                a["numero"] = next_n - 1
            else:
                continue
            a["numero_inferido"] = True
            changed = True

    if asientos and all(a["numero"] is None for a in asientos):
        start = last_declared - len(asientos) + 1 if last_declared is not None else 0
        for i, a in enumerate(asientos):
            a["numero"] = max(start, 0) + i
            a["numero_inferido"] = True


def current_owners(asientos: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """People of the highest-numbered asiento that lists titulares -- a
    convenience for the reviewer, not a legal determination (partial transfers,
    usufructs etc. still need reading the asientos)."""
    for a in sorted(asientos, key=lambda x: x.get("numero") if x.get("numero") is not None else -1, reverse=True):
        owners = [p for p in a.get("personas", []) if p.get("rol") == "titular"]
        if owners:
            return [
                {"nombre": p.get("nombre"), "ci": p.get("ci"), "proporcion": p.get("proporcion"), "asiento": a.get("numero")}
                for p in owners
            ]
    return []
