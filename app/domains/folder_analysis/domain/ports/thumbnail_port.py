from abc import ABC, abstractmethod


class ThumbnailPort(ABC):
    """Makes the smaller copies of a photo the web shows. The originals are phone
    photos of several megabytes: sending them whole is what makes a screen of
    photos slow, so nothing but the zoomed viewer ever asks for one."""

    @abstractmethod
    def make(self, content: bytes) -> bytes:
        """Small JPEG preview for a list row. Raises InvalidCaptureException if
        `content` is not a readable image -- which is also how uploads are
        validated."""

    @abstractmethod
    def preview(self, content: bytes) -> bytes:
        """Web-sized JPEG: big enough to read a folio on screen, a fraction of
        the original's weight. Raises InvalidCaptureException like `make`."""
