"""
Header block of page 1 of a `folio real` (above the A/B/C columns): matrícula,
tipo de inmueble, ubicación, designación S/TIT, superficie, medidas, linderos
N/S/E/O and propiedad.

Rule-based on purpose (no LLM): it is a fixed printed form, so every value sits
at a known place relative to its printed label. Two quirks seen on a real folio
shape the rules:

- Values are typed ~half a line LOWER than their label (label and value come
  from different print passes), so "same row" means a window that starts a bit
  above the label's center and reaches a line and a half below it.
- The right half of the header holds unrelated stamps (timbre, fecha y hora,
  código de barras), so left-column values only take blocks that start left of
  the right-hand labels (CATASTRO / PROPIEDAD).
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.domains.folios.domain.entities.ocr_block import OcrBlock
from app.domains.folios.domain.services.text import (
    compact,
    find_label,
    group_lines,
    join_text,
    min_confidence,
    normalize,
    strip_filler,
)

_MATRICULA_RE = re.compile(r"\d{1,2}\.\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{4,10}")
_LINDERO_RE = re.compile(r"^\s*(NORTE|SUD|SUR|ESTE|OESTE|N|S|E|O)\s*[.,:;]+\s*[.:]?\s*(.*)$")
_DIRECTIONS = {
    "N": "norte", "NORTE": "norte",
    "S": "sud", "SUD": "sud", "SUR": "sud",
    "E": "este", "ESTE": "este",
    "O": "oeste", "OESTE": "oeste",
}
_STATUS_WORDS = ("VIGENTE", "CERRAD", "CANCELAD", "INACTIV", "BLOQUEAD", "ANULAD")


@dataclass
class HeaderResult:
    data: Dict[str, Any]
    confidence: Dict[str, Optional[float]] = field(default_factory=dict)
    observations: List[str] = field(default_factory=list)


def _tidy(text: str) -> str:
    """Filler out, and the most common OCR spacing glitches around 'N°' fixed:
    'LOTESN°1.Y2' -> 'LOTES N° 1.Y2', 'N°22' -> 'N° 22'."""
    t = strip_filler(text)
    t = re.sub(r"(?<=[A-Za-z])N\s*[°º]", " N°", t)
    t = re.sub(r"N\s*[°º]\s*(?=\d)", "N° ", t)
    return re.sub(r"\s+", " ", t).strip()


def _row_values(
    label: OcrBlock, blocks: Sequence[OcrBlock], x_limit: float, exclude: Sequence[OcrBlock]
) -> List[OcrBlock]:
    """Blocks to the right of a label, in its (slightly lower) value row."""
    lo, hi = label.cy - 0.3 * label.h, label.cy + 1.5 * label.h
    out = [
        b for b in blocks
        if b is not label and b not in exclude
        and b.x0 >= label.x1 - 0.5 * label.h
        and b.x0 < x_limit
        and lo <= b.cy <= hi
    ]
    return sorted(out, key=lambda b: b.x0)


def _parse_surface(text: str) -> Tuple[Optional[float], Optional[str]]:
    t = normalize(text).replace("*", " ")
    m = re.search(r"\d[\d.,]*", t)
    value = None
    if m:
        raw = m.group(0).rstrip(".,")
        if "," in raw and "." in raw:
            # Whichever separator comes last is the decimal one.
            raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(",", ".") if len(raw.split(",")[-1]) != 3 else raw.replace(",", "")
        elif raw.count(".") > 1:
            head, _, tail = raw.rpartition(".")
            raw = head.replace(".", "") + "." + tail
        try:
            value = float(raw)
        except ValueError:
            value = None
    unit = None
    if re.search(r"HECT|\bHAS?\b", t):
        unit = "ha"
    elif re.search(r"METRO|MTS|\bM2\b|\bM\b", t):
        unit = "m2"
    return value, unit


def parse_header(blocks: Sequence[OcrBlock], width: float) -> HeaderResult:
    blocks = [b for b in blocks if b.text.strip()]
    labels = {
        "matricula": find_label(blocks, "MATRICULA"),
        "ubicacion": find_label(blocks, "UBICACION"),
        "designacion": find_label(blocks, "DESIGNACION"),
        "superficie": find_label(blocks, "SUPERFICIE"),
        "medidas": find_label(blocks, "MEDIDAS"),
        "linderos": find_label(blocks, "LINDEROS"),
        "propiedad": find_label(blocks, "PROPIEDAD"),
        "catastro": find_label(blocks, "CATASTRO"),
    }
    label_blocks = [b for b in labels.values() if b is not None]
    right_labels = [labels[k] for k in ("catastro", "propiedad") if labels[k] is not None]
    x_limit = min((b.x0 for b in right_labels), default=width * 0.55) - 5

    data: Dict[str, Any] = {}
    conf: Dict[str, Optional[float]] = {}
    obs: List[str] = []

    # ---- Matrícula: number + status on one row, registry zone just above.
    number_block = None
    for b in blocks:
        m = _MATRICULA_RE.search(b.text.replace(" ", "").replace(",", "."))
        if m:
            number_block, number = b, m.group(0)
            break
    matricula: Dict[str, Optional[str]] = {"numero": None, "estado": None, "zona": None}
    if number_block is not None:
        matricula["numero"] = number
        conf["matricula.numero"] = round(number_block.confidence, 4)
        status = next(
            (
                b for b in blocks
                if b is not number_block and abs(b.cy - number_block.cy) < number_block.h
                and b.x0 > number_block.x0 and any(w in normalize(b.text) for w in _STATUS_WORDS)
            ),
            None,
        )
        if status is not None:
            matricula["estado"] = normalize(status.text)
            conf["matricula.estado"] = round(status.confidence, 4)
        zone = min(
            (
                b for b in blocks
                if "," in b.text and b.cy < number_block.cy and number_block.cy - b.cy < 2.5 * number_block.h
                and b not in label_blocks and b.x0 < x_limit
            ),
            key=lambda b: abs(b.cx - number_block.cx),
            default=None,
        )
        if zone is not None:
            matricula["zona"] = _tidy(zone.text)
            conf["matricula.zona"] = round(zone.confidence, 4)
    else:
        obs.append("No se encontró el número de matrícula.")
    data["matricula"] = matricula

    # ---- Tipo de inmueble: the parenthesised line under the matrícula, "(Lote de Terreno)".
    kind = next(
        (
            b for b in sorted(blocks, key=lambda b: b.cy)
            if re.fullmatch(r"\(.+\)", strip_filler(b.text)) and b.x0 < x_limit
            and (number_block is None or b.cy > number_block.cy)
        ),
        None,
    )
    data["tipo_inmueble"] = strip_filler(kind.text)[1:-1].strip() if kind is not None else None
    if kind is not None:
        conf["tipo_inmueble"] = round(kind.confidence, 4)

    # ---- Simple "LABEL: value" rows of the left column.
    used: List[OcrBlock] = list(label_blocks) + [x for x in (number_block, kind) if x is not None]
    for key, label_key in (
        ("ubicacion", "ubicacion"),
        ("designacion_s_tit", "designacion"),
        ("superficie_texto", "superficie"),
        ("medidas", "medidas"),
    ):
        label = labels[label_key]
        if label is None:
            data[key] = None
            obs.append(f"No se encontró el rótulo {label_key.upper()}.")
            continue
        values = _row_values(label, blocks, x_limit, used)
        used.extend(values)
        data[key] = _tidy(join_text(values)) or None
        conf[key] = min_confidence(values)

    surface_text = data.pop("superficie_texto")
    if surface_text:
        # The superscript in 'Metros ²' comes out as 'z' / '2' / '²'.
        surface_text = re.sub(r"(?i)\b(metros?|mts?)\.?\s*[z2²]$", r"\1 2", surface_text)
    surface_conf = conf.pop("superficie_texto", None)
    value, unit = _parse_surface(surface_text or "")
    data["superficie"] = {"valor": value, "unidad": unit, "texto_original": surface_text}
    conf["superficie"] = surface_conf
    if surface_text and value is None:
        obs.append("No se pudo leer el valor numérico de la superficie.")

    # ---- Linderos: 'N.:CON ...' blocks from the LINDEROS row down (S/O are on the right half).
    data["linderos"], lconf = _parse_linderos(blocks, labels["linderos"], used)
    conf.update(lconf)
    missing = [k for k, v in data["linderos"].items() if not v]
    if missing:
        obs.append("Linderos sin leer: " + ", ".join(missing) + ".")

    # ---- Propiedad: value printed UNDER its label, right column.
    prop_label = labels["propiedad"]
    prop = None
    if prop_label is not None:
        prop = min(
            (
                b for b in blocks
                if b is not prop_label and b not in used
                and prop_label.cy + 0.3 * prop_label.h < b.cy <= prop_label.cy + 2.5 * prop_label.h
                and prop_label.x0 - 2 * prop_label.h <= b.x0 <= prop_label.x1 + 4 * prop_label.h
            ),
            key=lambda b: b.cy,
            default=None,
        )
        if prop is None:  # sometimes on the same row, to the right
            same_row = _row_values(prop_label, blocks, float("inf"), used)
            prop = same_row[0] if same_row else None
    data["propiedad"] = _tidy(prop.text) if prop is not None else None
    if prop is not None:
        conf["propiedad"] = round(prop.confidence, 4)

    # ---- Antecedente dominial (sometimes printed right above the columns).
    ante = next((b for b in blocks if "ANTECEDENTE" in compact(b.text) or "DOMINIAL" in compact(b.text)), None)
    if ante is not None:
        text = ante.text.split(":", 1)[1] if ":" in ante.text else ""
        data["antecedente_dominial"] = _tidy(text) or None
    else:
        data["antecedente_dominial"] = None

    return HeaderResult(data=data, confidence=conf, observations=obs)


def _parse_linderos(
    blocks: Sequence[OcrBlock], label: Optional[OcrBlock], used: Sequence[OcrBlock]
) -> Tuple[Dict[str, Optional[str]], Dict[str, Optional[float]]]:
    result: Dict[str, Optional[str]] = {"norte": None, "sud": None, "este": None, "oeste": None}
    conf: Dict[str, Optional[float]] = {}
    if label is not None:
        candidates = [b for b in blocks if b is not label and b.cy >= label.y0 - 0.3 * label.h]
    else:
        candidates = list(blocks)
    candidates = [b for b in candidates if b not in used or _LINDERO_RE.match(normalize(b.text))]

    parts: Dict[str, List[OcrBlock]] = {}
    current: Optional[str] = None
    previous_line_starts: List[Tuple[str, float]] = []
    for line in group_lines(candidates):
        line_starts: List[Tuple[str, float]] = []
        current = None
        for b in line:
            m = _LINDERO_RE.match(normalize(b.text))
            direction = _DIRECTIONS.get(m.group(1)) if m else None
            if direction and result[direction] is None and direction not in parts:
                current = direction
                parts[current] = [b]
                line_starts.append((current, b.x0))
            elif current is not None:
                parts[current].append(b)  # continuation on the same row
            elif previous_line_starts:
                # Wrapped value: continues the lindero of the previous row whose
                # start is horizontally closest.
                direction = min(previous_line_starts, key=lambda s: abs(s[1] - b.x0))[0]
                if abs(dict(previous_line_starts)[direction] - b.x0) < 6 * b.h:
                    parts[direction].append(b)
        previous_line_starts = line_starts or previous_line_starts

    for direction, blks in parts.items():
        head = blks[0].text.strip()
        first = _LINDERO_RE.match(head.upper())
        # Keep the original casing of the value: cut the 'N.:' prefix by length.
        prefix_len = len(head) - len(first.group(2)) if first else 0
        text = " ".join([head[prefix_len:]] + [b.text.strip() for b in blks[1:]])
        result[direction] = _tidy(text) or None
        conf[f"linderos.{direction}"] = min_confidence(blks)
    return result, conf
