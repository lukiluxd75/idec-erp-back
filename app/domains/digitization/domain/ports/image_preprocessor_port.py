from abc import ABC, abstractmethod


class ImagePreprocessorPort(ABC):
    @abstractmethod
    def prepare(self, content: bytes) -> bytes:
        """Normalized image ready for the vision model. Raises
        InvalidDocumentException if the bytes are not a readable image."""
