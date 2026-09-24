from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple

Rect = Tuple[int, int, int, int]  # x0, y0, x1, y1 (pixels)
Affine = Tuple[Tuple[float, float, float], Tuple[float, float, float]]  # 2x3 matrix


@dataclass(frozen=True)
class RotatedImage:
    content: bytes  # JPEG
    width: int
    height: int
    # Maps a point of the source image onto this one (x' = M·[x, y, 1]) -- lets
    # the pipeline reuse the OCR it already ran on the source instead of paying
    # another OCR call just to learn where things moved.
    matrix: Affine


class PageImagePort(ABC):
    """Computer-vision operations the pipeline needs on a page photo. Byte-in /
    byte-out on purpose: domain and application never see an image library type
    (the adapter is OpenCV -- infrastructure/opencv_page_image.py)."""

    @abstractmethod
    def normalize(self, content: bytes) -> Tuple[bytes, int, int]:
        """Decode (honoring EXIF orientation), cap the size, re-encode as JPEG.
        Returns (jpeg, width, height). Raises InvalidFolioUploadException if the
        bytes are not a decodable image."""

    @abstractmethod
    def rotate(self, content: bytes, angle_ccw_deg: float) -> RotatedImage:
        """Rotate counter-clockwise by any angle, enlarging the canvas so nothing
        is cropped (white fill)."""

    @abstractmethod
    def vertical_lines(self, content: bytes) -> List[float]:
        """X positions of long vertical ruling lines (the form's table borders),
        left to right."""

    @abstractmethod
    def crop(self, content: bytes, rect: Rect) -> bytes:
        """JPEG of that region (clamped to the image)."""
