from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domains.folder_analysis.domain.entities import QueuedJob


class ExtractionQueuePort(ABC):
    """The shared queue that runs extractions on the architects' PCs."""

    @abstractmethod
    def submit(
        self,
        *,
        content: bytes,
        file_name: str,
        mime_type: str,
        requested_by: str,
        instructions: Optional[str],
        output_template: Optional[Dict[str, Any]],
    ) -> str:
        """Enqueue one page image. Returns the job id."""

    @abstractmethod
    def status(self, job_ids: List[str]) -> Dict[str, QueuedJob]: ...
