from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


class FolioExtractionPort(ABC):
    """Reads a folio real from its photos with OCR and rules, without the vision
    model. Takes seconds per photo, so it never runs inside a request."""

    @abstractmethod
    def extract(
        self,
        pages: Sequence[bytes],
        on_page: Optional[Callable[[int], None]] = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """All the photos of one document, in page order -> (data in the lane's
        shape, observations for the architect).

        `on_page(index)` is called as each photo is finished, so the screen can
        show how many are left while the rest are still running."""
