"""
Detección de la planta de una página del plano a partir de su TÍTULO
("PLANTA SEMISOTANO", "PLANTA 1° PISO", "PLANTA TIPO 2° - 4° PISO"...), que
el dibujante siempre escribe con la letra más grande del plano, cerca de la
escala ("ESC: 1:100").

Puro (sin OCR ni base): recibe los bloques del OCR y devuelve las plantas de
PLANTAS_RESUMEN que corresponden, más el detalle para depurar. Si no hay un
título claro NO adivina: devuelve plantas vacías y el motivo, y la página
queda "sin asignar" para que la corrijan a mano en la web.

Trampa conocida: los rótulos de unidades dúplex también dicen "planta"
("DEPARTAMENTO A DUPLEX (PLANTA BAJA", "5° PISO +PLANTA ALTA 6° PISO"). Por
eso se exige que el bloque sea ENTERO un título, no que lo contenga.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

from app.domains.resolutions.domain.plantas import PLANTAS_RESUMEN

PISO_MAXIMO = 30


@dataclass(frozen=True)
class TitleBlock:
    """Un bloque del OCR: texto y su rectángulo en la imagen."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def tamano_letra(self) -> float:
        return min(self.x1 - self.x0, self.y1 - self.y0)


@dataclass
class PlantaDetection:
    plantas: List[str] = field(default_factory=list)
    titulo: Optional[str] = None
    motivo: Optional[str] = None
    candidatos: List[dict] = field(default_factory=list)


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").upper()
    # Marcas de ordinal y lo que el OCR lee en su lugar ("1 ° PISO", "2º").
    t = re.sub(r"[°º˚ª]", " ", t)
    t = re.sub(r"[^A-Z0-9\- ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# El OCR confunde el 0 con la O ("PIS0") y la I con el 1 ("I00"): se corrigen solo dentro de las palabras del título.
_PISO = r"PIS[O0]"
_ORDINAL = r"(?:ER|RO|DO|TO|VO|NO|MO)?"
_NUM = r"(\d{1,2}|[IL])"

# Los espacios son opcionales: el OCR suele leer el título de estos planos
# pegado (".PLANTABAJA..", "PLANTA1°PISO.") -- los puntos y marcas de ordinal
# ya los saca _normalizar.
_RE_ESPECIAL = re.compile(r"^PLANTA ?(SEMI ?SOTANO|SOTANO|[BS8]AJA)$")
_RE_PISOS = re.compile(
    rf"^PLANTA ?(?:TIPO ?)?{_NUM} ?{_ORDINAL}(?: ?(?:-|A|AL|Y) ?{_NUM} ?{_ORDINAL})? ?{_PISO}$"
)


def _numero(s: str) -> int:
    return 1 if s in ("I", "L") else int(s)


def plantas_de_titulo(texto: str) -> Optional[List[str]]:
    """Plantas (nombres de PLANTAS_RESUMEN) si `texto` es ENTERO un título de
    planta; None si no lo es."""
    t = _normalizar(texto)
    m = _RE_ESPECIAL.match(t)
    if m:
        nombre = "SEMISOTANO" if m.group(1).startswith("SEMI") else ("BAJA" if m.group(1).endswith("AJA") else m.group(1))
        return [f"PLANTA {nombre}"]
    m = _RE_PISOS.match(t)
    if not m:
        return None
    desde = _numero(m.group(1))
    hasta = _numero(m.group(2)) if m.group(2) else desde
    if not (1 <= desde <= hasta <= PISO_MAXIMO):
        return None
    plantas = [f"PLANTA {n}º PISO" for n in range(desde, hasta + 1)]
    return plantas if all(p in PLANTAS_RESUMEN for p in plantas) else None


def _pegados(a: TitleBlock, b: TitleBlock) -> bool:
    """¿`b` sigue a `a` en la misma línea del título? (misma altura de letra y
    separados por menos de dos letras, en horizontal o en vertical)."""
    ta, tb = a.tamano_letra, b.tamano_letra
    if ta <= 0 or tb <= 0 or not (0.7 <= tb / ta <= 1.4):
        return False
    hueco_x = max(b.x0 - a.x1, a.x0 - b.x1, 0)
    hueco_y = max(b.y0 - a.y1, a.y0 - b.y1, 0)
    return max(hueco_x, hueco_y) <= 2 * ta and min(hueco_x, hueco_y) == 0


def _unir(a: TitleBlock, b: TitleBlock) -> TitleBlock:
    return TitleBlock(
        f"{a.text} {b.text}", min(a.x0, b.x0), min(a.y0, b.y0), max(a.x1, b.x1), max(a.y1, b.y1)
    )


def detect_plantas(bloques: List[TitleBlock]) -> PlantaDetection:
    """Busca el título de planta entre los bloques del OCR de una página."""
    candidatos = []
    for b in bloques:
        plantas = plantas_de_titulo(b.text)
        if plantas:
            candidatos.append((b, plantas))
    if not candidatos:
        # El OCR a veces parte el título en dos bloques ("PLANTA TIPO" / "2° - 4° PISO"): se prueba cada par de bloques pegados.
        for a in bloques:
            for b in bloques:
                if a is b or not _pegados(a, b):
                    continue
                union = _unir(a, b)
                plantas = plantas_de_titulo(union.text)
                if plantas:
                    candidatos.append((union, plantas))
    detalle = [
        {"texto": b.text, "plantas": p, "tamano_letra": round(b.tamano_letra, 1)} for b, p in candidatos
    ]
    if not candidatos:
        return PlantaDetection(motivo="no se encontró un título de planta en el plano", candidatos=detalle)

    # El título es el texto más grande del plano.
    candidatos.sort(key=lambda c: -c[0].tamano_letra)
    mejor, plantas = candidatos[0]
    for otro, otras in candidatos[1:]:
        if otras != plantas and otro.tamano_letra >= 0.8 * mejor.tamano_letra:
            return PlantaDetection(
                motivo=f'hay dos títulos distintos: "{mejor.text}" y "{otro.text}"', candidatos=detalle
            )
    return PlantaDetection(plantas=plantas, titulo=mejor.text, candidatos=detalle)
