"""
Text helpers for the lanes that read a form with rules instead of the vision
model. Same job as the folio parsers' helpers, kept here because a domain never
imports another domain's insides (CLAUDE.md §2) -- the OCR blocks arrive through
the folios contract, and everything below only needs their text and their box.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Protocol, Sequence


class Block(Protocol):
    """What these helpers need of an OCR block (folios' contract TextBlock fits)."""

    text: str
    confidence: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float: ...

    @property
    def cy(self) -> float: ...

    @property
    def h(self) -> float: ...


_EDGE_JUNK = re.compile(r"^[\s\-_*+#=~.:,;|%]+|[\s\-_*+#=~:,;|]+$")


def normalize(text: str) -> str:
    """Uppercase, no accents, single spaces."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.upper()).strip()


def compact(text: str) -> str:
    """normalize() with only letters and digits kept -- for label matching that
    survives the OCR gluing or splitting words ("COD. CAT." -> "CODCAT")."""
    return re.sub(r"[^A-Z0-9]", "", normalize(text))


def clean_value(text: str) -> Optional[str]:
    """A value as it should be stored: no leading colon, no box borders the OCR
    read as dashes or pipes, single spaces. None when nothing is left."""
    return re.sub(r"\s+", " ", _EDGE_JUNK.sub("", text or "")).strip() or None


_LOOKALIKE = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})


def label_key(text: str) -> str:
    """compact() with the letter/digit lookalikes folded together: what labels are
    matched on."""
    return compact(text).translate(_LOOKALIKE)


def after_label(block_text: str, label: str) -> Optional[str]:
    """The rest of the block once `label` is taken off its front, or None when
    there is nothing left.

    The OCR often returns a label and its value as ONE block, and drops the spaces
    while doing it ("BASEIMPONIBLE:350000.00"). Counting letters and digits -- not
    characters -- is what lets the value be cut off cleanly no matter how the
    punctuation and spacing came out."""
    wanted = len(label_key(label))
    seen = 0
    for index, char in enumerate(block_text or ""):
        if char.isalnum():
            seen += 1
            if seen == wanted:
                return clean_value(block_text[index + 1 :])
    return None


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def contains(needle: str, haystack: str, min_ratio: float = 0.88) -> bool:
    """Is `needle` in `haystack` (both compacted), allowing OCR noise? This is
    what keeps the LLM pass honest: a value it proposes must be on the photo."""
    n, h = compact(needle), compact(haystack)
    if not n:
        return False
    if n in h:
        return True
    if len(n) > len(h):
        return False
    return max(similar(h[i : i + len(n)], n) for i in range(len(h) - len(n) + 1)) >= min_ratio


def label_score(block_text: str, label: str) -> float:
    """How well a block reads as `label`. 1+ when the block starts with it (and
    higher the less there is left over, so the block that is ONLY the label wins
    over one that also carries its value), otherwise the fuzzy ratio of its first
    characters."""
    target, c = label_key(label), label_key(block_text)
    if not target or not c:
        return 0.0
    if c.startswith(target):
        return 1.0 + len(target) / max(len(c), 1)
    return similar(c[: len(target) + 1], target)


def group_lines(blocks: Sequence[Block]) -> List[List[Block]]:
    """Cluster blocks into text lines (same baseline within half a line height),
    each line left to right, lines top to bottom."""
    lines: List[List[Block]] = []
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


def join_text(blocks: Iterable[Block]) -> str:
    return " ".join(b.text.strip() for b in blocks if b.text.strip())


def min_confidence(blocks: Iterable[Block]) -> Optional[float]:
    values = [b.confidence for b in blocks]
    return round(min(values), 4) if values else None
