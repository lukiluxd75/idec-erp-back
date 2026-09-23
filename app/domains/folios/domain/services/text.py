"""Text helpers shared by the folio parsers. The folio is typewritten text padded
with filler runs ("-----", "*****", "#####") and the OCR service drops or glues
spaces now and then, so every comparison goes through these."""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Optional

from app.domains.folios.domain.entities.ocr_block import OcrBlock

_FILLER_RUN = re.compile(r"[-_*+#=~.]{3,}")
_EDGE_JUNK = re.compile(r"^[\s\-_*+#=~.:,;]+|[\s\-_*+#=~,;]+$")


def normalize(text: str) -> str:
    """Uppercase, no accents, single spaces."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.upper()).strip()


def compact(text: str) -> str:
    """normalize() with only letters and digits kept -- for fuzzy label matching
    that survives glued/split words ("MATRiCULA N°" -> "MATRICULAN")."""
    return re.sub(r"[^A-Z0-9]", "", normalize(text))


def strip_filler(text: str) -> str:
    """Drop the typewriter filler runs and junk at the edges, keep the content.
    'Asiento Numero: 1-------' -> 'Asiento Numero: 1'."""
    t = _FILLER_RUN.sub(" ", text or "")
    t = _EDGE_JUNK.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def is_filler(text: str) -> bool:
    """Nothing but filler / registrar-initials codes ('[GPF]-[GPF]-[GPF]')."""
    t = re.sub(r"\[[A-Z]{2,4}\]", "", normalize(text))
    return not re.sub(r"[^A-Z0-9]", "", t)


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_label(blocks: Iterable[OcrBlock], label: str, min_ratio: float = 0.8) -> Optional[OcrBlock]:
    """Block whose compacted text starts with (or fuzzily matches) `label` --
    labels print alone on their block ('SUPERFICIE:') but OCR may add/drop a
    letter. Best match wins."""
    target = compact(label)
    best, best_score = None, 0.0
    for b in blocks:
        c = compact(b.text)
        if not c:
            continue
        if c.startswith(target):
            score = 1.0 + len(target) / max(len(c), 1)  # prefer the block that is ONLY the label
        else:
            score = similar(c[: len(target) + 1], target)
        if score > best_score:
            best, best_score = b, score
    return best if best_score >= min_ratio else None


def group_lines(blocks: List[OcrBlock]) -> List[List[OcrBlock]]:
    """Cluster blocks into text lines (same baseline within half a line height),
    each line sorted left to right, lines top to bottom."""
    lines: List[List[OcrBlock]] = []
    for b in sorted(blocks, key=lambda b: b.cy):
        if lines:
            last = lines[-1]
            ref_cy = sum(x.cy for x in last) / len(last)
            ref_h = max(sum(x.h for x in last) / len(last), 1.0)
            if abs(b.cy - ref_cy) <= 0.5 * max(ref_h, b.h):
                last.append(b)
                continue
        lines.append([b])
    return [sorted(line, key=lambda b: b.x0) for line in lines]


def join_text(blocks: Iterable[OcrBlock]) -> str:
    return " ".join(b.text.strip() for b in blocks if b.text.strip())


def min_confidence(blocks: Iterable[OcrBlock]) -> Optional[float]:
    values = [b.confidence for b in blocks]
    return round(min(values), 4) if values else None
