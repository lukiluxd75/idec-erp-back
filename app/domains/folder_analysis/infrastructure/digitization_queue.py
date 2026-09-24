from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.domains.digitization.contracts import get_jobs, submit_image
from app.domains.folder_analysis.domain.entities import QueuedJob
from app.domains.folder_analysis.domain.ports import ExtractionQueuePort

SOURCE = "folder_analysis"


class DigitizationQueue(ExtractionQueuePort):
    """Adapter over the digitization domain's public contract (CLAUDE.md §2)."""

    def __init__(self, db: Session):
        self._db = db

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
        return submit_image(
            self._db,
            content=content,
            file_name=file_name,
            mime_type=mime_type,
            requested_by=requested_by,
            instructions=instructions,
            output_template=output_template,
            source=SOURCE,
        )

    def status(self, job_ids: List[str]) -> Dict[str, QueuedJob]:
        return {
            job_id: QueuedJob(status=view.status, result=view.result, error=view.error)
            for job_id, view in get_jobs(self._db, job_ids).items()
        }
