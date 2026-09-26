from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence, Tuple


class FolioExtractionPort(ABC):
    """Reads a folio real from its photos with OCR and rules, without the vision
    model. Takes seconds per photo, so it never runs inside a request."""

    @abstractmethod
    def extract(self, pages: Sequence[bytes]) -> Tuple[Dict[str, Any], List[str]]:
        """All the photos of one document, in page order -> (data in the lane's
        shape, observations for the architect)."""
