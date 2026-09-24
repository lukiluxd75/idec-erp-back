from typing import List

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.domains.digitization.application.use_cases import (
    GetJobUseCase,
    ListJobsUseCase,
    RetryJobUseCase,
    SubmitDocumentUseCase,
)
from app.domains.digitization.presentation.deps import (
    get_get_job_use_case,
    get_list_jobs_use_case,
    get_retry_job_use_case,
    get_submit_document_use_case,
)
from app.domains.digitization.presentation.schemas.job_schema import JobDetail, JobSummary
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/jobs", tags=["Digitization · Jobs"])


@router.post("", response_model=JobSummary, status_code=status.HTTP_202_ACCEPTED)
def submit_document(
    file: UploadFile = File(...),
    use_case: SubmitDocumentUseCase = Depends(get_submit_document_use_case),
    user: UserProfile = Depends(require_permission("digitization.edit")),
):
    """Enqueue an image for digitization. Returns immediately; poll GET /jobs/{id}."""
    job = use_case.execute(
        file_name=file.filename or "",
        mime_type=file.content_type or "",
        content=file.file.read(),
        requested_by=user.sub,
    )
    return JobSummary.from_entity(job)


@router.get("", response_model=List[JobSummary])
def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    use_case: ListJobsUseCase = Depends(get_list_jobs_use_case),
    user: UserProfile = Depends(require_permission("digitization.view")),
):
    return [JobSummary.from_entity(job) for job in use_case.execute(user.sub, limit)]


@router.get("/{job_id}", response_model=JobDetail)
def get_job(
    job_id: str,
    use_case: GetJobUseCase = Depends(get_get_job_use_case),
    user: UserProfile = Depends(require_permission("digitization.view")),
):
    return JobDetail.from_entity(use_case.execute(job_id, user.sub))


@router.post("/{job_id}/retry", response_model=JobSummary)
def retry_job(
    job_id: str,
    use_case: RetryJobUseCase = Depends(get_retry_job_use_case),
    user: UserProfile = Depends(require_permission("digitization.edit")),
):
    return JobSummary.from_entity(use_case.execute(job_id, user.sub))
