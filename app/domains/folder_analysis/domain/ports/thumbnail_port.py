from abc import ABC, abstractmethod


class ThumbnailPort(ABC):
    @abstractmethod
    def make(self, content: bytes) -> bytes:
        """Small JPEG preview. Raises InvalidCaptureException if `content` is not a
        readable image -- which is also how uploads are validated."""
