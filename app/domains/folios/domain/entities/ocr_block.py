"""A text block as returned by the OCR service, reduced to an axis-aligned box.
Pure domain value: parsers and layout reason only in terms of these, never in
terms of the OCR service's raw JSON or of image libraries."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OcrBlock:
    text: str
    confidence: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    def shifted(self, dx: float, dy: float) -> "OcrBlock":
        """Same block in another coordinate frame (e.g. crop -> full page)."""
        return OcrBlock(self.text, self.confidence, self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "box": [round(self.x0), round(self.y0), round(self.x1), round(self.y1)],
        }
