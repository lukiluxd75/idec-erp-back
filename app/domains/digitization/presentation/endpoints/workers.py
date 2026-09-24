from typing import List

from fastapi import APIRouter, Depends

from app.domains.digitization.application.use_cases import CheckWorkersUseCase
from app.domains.digitization.presentation.deps import get_check_workers_use_case
from app.domains.digitization.presentation.schemas.job_schema import WorkerStatusResponse
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/workers", tags=["Digitization · Workers"])


@router.get("", response_model=List[WorkerStatusResponse])
def list_workers(
    use_case: CheckWorkersUseCase = Depends(get_check_workers_use_case),
    _user: UserProfile = Depends(require_permission("digitization.view")),
):
    """Live status of each architect PC: reachable, model installed, current job."""
    return [WorkerStatusResponse.from_entity(s) for s in use_case.execute()]
