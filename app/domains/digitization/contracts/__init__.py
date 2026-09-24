"""
Public entry point of the digitization domain for other domains (CLAUDE.md §2).
Another domain enqueues an image with its own extraction instructions and later
reads the job status; the queue, the PCs and the model stay hidden behind this.

    from app.domains.digitization.contracts import submit_image, get_jobs

    job_id = submit_image(db, content=..., file_name="p1.jpg", mime_type="image/jpeg",
                          requested_by=user.sub, instructions="...", output_template={...},
                          source="folder_analysis")
    views = get_jobs(db, [job_id])   # {job_id: JobView}

It also lends the architects' PCs to other domains that run their own Ollama
work on them (see get_worker_host_picker / get_borrow_host).
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.core.database.connection import SessionLocal
from app.domains.digitization.application.use_cases import (
    BorrowHostUseCase,
    GetJobsUseCase,
    PickWorkerHostsUseCase,
    SubmitDocumentUseCase,
)
from app.domains.digitization.domain.entities import JobStatus
from app.domains.digitization.infrastructure.config import get_digitization_settings
from app.domains.digitization.infrastructure.sql_job_repository import SqlJobRepository
from app.domains.digitization.presentation.deps import (
    build_job_repository,
    get_host_usage,
    get_max_upload_bytes,
    get_preprocessor,
    get_vision_worker,
)

__all__ = [
    "BorrowHostUseCase",
    "JobStatus",
    "JobView",
    "PickWorkerHostsUseCase",
    "get_borrow_host",
    "get_jobs",
    "get_worker_host_picker",
    "submit_image",
]


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


def _busy_hosts() -> Set[str]:
    with SessionLocal() as db:
        jobs = {job.worker_host for job in SqlJobRepository(db).list_processing() if job.worker_host}
    return jobs | set(get_host_usage().active())


@lru_cache()
def get_worker_host_picker() -> PickWorkerHostsUseCase:
    """Lets another domain send its own Ollama work to the same architects' PCs.
    `execute(model)` returns [] when DIGITIZATION_WORKER_URLS is empty or no PC has
    that model, so the caller keeps whatever fallback it had."""
    settings = get_digitization_settings()
    return PickWorkerHostsUseCase(get_vision_worker(), settings.worker_hosts, _busy_hosts)


@lru_cache()
def get_borrow_host(used_by: str) -> BorrowHostUseCase:
    """`execute(host, seconds)` is a context manager: while it is open the monitor
    screen shows that PC as working, labelled with `used_by` (the domain name)."""
    return BorrowHostUseCase(get_host_usage(), used_by)
