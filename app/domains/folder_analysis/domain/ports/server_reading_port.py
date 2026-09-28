from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


class ServerReadingPort(ABC):
    """A lane that reads its own document here on the server (OCR and rules)
    instead of queueing it to the architects' PCs. Takes seconds per photo, so it
    never runs inside a request: RunServerReadingUseCase drives it from a
    BackgroundTask.

    One port, one use case, one shape of result -- the lanes only differ in the
    form they read (see FolioExtractionPort, TaxExtractionPort)."""

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
