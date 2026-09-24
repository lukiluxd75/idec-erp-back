"""
Public entry point of the digitization domain for other domains (CLAUDE.md §2).
Another domain enqueues an image with its own extraction instructions and later
reads the job status; the queue, the PCs and the model stay hidden behind this.

    from app.domains.digitization.contracts import submit_image, get_jobs

    job_id = submit_image(db, content=..., file_name="p1.jpg", mime_type="image/jpeg",
                          requested_by=user.sub, instructions="...", output_template={...},
                          source="folder_analysis")
    views = get_jobs(db, [job_id])   # {job_id: JobView}
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.domains.digitization.application.use_cases import GetJobsUseCase, SubmitDocumentUseCase
from app.domains.digitization.domain.entities import JobStatus
from app.domains.digitization.presentation.deps import build_job_repository, get_max_upload_bytes, get_preprocessor


@dataclass(frozen=True)
class JobView:
    id: str
    status: str
    attempts: int
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def submit_image(
    db: Session,
    *,
    content: bytes,
    file_name: str,
    mime_type: str,
    requested_by: str,
    instructions: Optional[str] = None,
    output_template: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
) -> str:
    """Validate, preprocess and enqueue one image. Raises InvalidDocumentException
    (HTTP 422 through the generic handler) for unreadable files. Returns the job id."""
    job = SubmitDocumentUseCase(build_job_repository(db), get_preprocessor(), get_max_upload_bytes()).execute(
        file_name=file_name,
        mime_type=mime_type,
        content=content,
        requested_by=requested_by,
        instructions=instructions,
        output_template=output_template,
        source=source,
    )
    return job.id


def get_jobs(db: Session, job_ids: List[str]) -> Dict[str, JobView]:
    """Current status of the given jobs. Unknown ids are simply absent."""
    return {
        job.id: JobView(id=job.id, status=job.status, attempts=job.attempts, result=job.result, error=job.error)
        for job in GetJobsUseCase(build_job_repository(db)).execute(job_ids)
    }


__all__ = ["JobStatus", "JobView", "get_jobs", "submit_image"]
