from typing import List

from fastapi import APIRouter, Depends

from app.domains.digitization.application.use_cases import CheckWorkersUseCase, StopWorkerUseCase
from app.domains.digitization.presentation.deps import get_check_workers_use_case, get_stop_worker_use_case
from app.domains.digitization.presentation.schemas.job_schema import (
    StopWorkerRequest,
    StopWorkerResponse,
    WorkerStatusResponse,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/workers", tags=["Digitization · Workers"])


@router.get("", response_model=List[WorkerStatusResponse])
def list_workers(
    use_case: CheckWorkersUseCase = Depends(get_check_workers_use_case),
    _user: UserProfile = Depends(require_permission("digitization.view")),
):
    """Live status of each architect PC: reachable, model installed, current job."""
    return [WorkerStatusResponse.from_entity(s) for s in use_case.execute()]


@router.post("/stop", response_model=StopWorkerResponse)
def stop_worker(
    body: StopWorkerRequest,
    use_case: StopWorkerUseCase = Depends(get_stop_worker_use_case),
    _user: UserProfile = Depends(require_permission("digitization.edit")),
):
    """Give up on whatever that PC is working on, whoever started it, and free it.
    Answers as soon as the request is noted; the PC itself lets go a second or two
    later, so the monitor still shows it busy on the next refresh or two."""
    stopped = use_case.execute(body.host)
    return StopWorkerResponse(host=stopped.host, used_by=stopped.used_by, job_id=stopped.job_id)
