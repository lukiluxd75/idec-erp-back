"""HTTP endpoints for the appraisal_review domain. The reviewer can only read appraisal
data and add observations — no field of the appraisal itself is ever editable here.
"""
import dataclasses

from fastapi import APIRouter, Depends, Query

from app.domains.appraisal_review.application.use_cases import (
    GetAppraisalDetailUseCase,
    ListPendingAppraisalsUseCase,
    MigrateAppraisalUseCase,
    SearchAppraisalsUseCase,
    SendObservationsUseCase,
)
from app.domains.appraisal_review.domain.entities import AppraisalDetail, AppraisalSummary
from app.domains.appraisal_review.presentation.deps import (
    get_appraisal_detail_use_case,
    get_list_pending_appraisals_use_case,
    get_migrate_appraisal_use_case,
    get_search_appraisals_use_case,
    get_send_observations_use_case,
)
from app.domains.appraisal_review.presentation.schemas import (
    AppraisalDetailOut,
    AppraisalSummaryOut,
    MigratedAppraisalOut,
    ObservationBatchOut,
    SendObservationsIn,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/appraisals", tags=["Appraisal Review"])


def _summary_to_schema(appraisal: AppraisalSummary) -> AppraisalSummaryOut:
    return AppraisalSummaryOut(**dataclasses.asdict(appraisal))


def _detail_to_schema(detail: AppraisalDetail) -> AppraisalDetailOut:
    return AppraisalDetailOut(**dataclasses.asdict(detail))


@router.get("", response_model=list[AppraisalSummaryOut])
def list_appraisals(
    form_number: str | None = Query(None, min_length=2, description="Búsqueda parcial por número de formulario"),
    list_use_case: ListPendingAppraisalsUseCase = Depends(get_list_pending_appraisals_use_case),
    search_use_case: SearchAppraisalsUseCase = Depends(get_search_appraisals_use_case),
    _user: UserProfile = Depends(require_permission("appraisal-review.view")),
):
    """Without `form_number`: appraisals the architect sent for review (status
    'submitted'). With `form_number`: appraisals matching that number regardless of
    status — Avalúos has its own separate login, so there is no automatic notification
    when one is created; this lets the reviewer pull it up directly."""
    if form_number:
        return [_summary_to_schema(a) for a in search_use_case.execute(form_number)]
    return [_summary_to_schema(a) for a in list_use_case.execute()]


@router.get("/{form_number}", response_model=AppraisalDetailOut)
def get_appraisal_detail(
    form_number: str,
    use_case: GetAppraisalDetailUseCase = Depends(get_appraisal_detail_use_case),
    _user: UserProfile = Depends(require_permission("appraisal-review.view")),
):
    return _detail_to_schema(use_case.execute(form_number))


@router.post("/{form_number}/observations", response_model=ObservationBatchOut)
def send_observations(
    form_number: str,
    payload: SendObservationsIn,
    use_case: SendObservationsUseCase = Depends(get_send_observations_use_case),
    user: UserProfile = Depends(require_permission("appraisal-review.edit")),
):
    """Sends the appraisal back to Avalúos with observations (status -> needs_correction)."""
    batch = use_case.execute(form_number, payload.observations, user.username)
    return ObservationBatchOut(**dataclasses.asdict(batch))


@router.post("/{form_number}/migrate", response_model=MigratedAppraisalOut)
def migrate_appraisal(
    form_number: str,
    use_case: MigrateAppraisalUseCase = Depends(get_migrate_appraisal_use_case),
    user: UserProfile = Depends(require_permission("appraisal-review.edit")),
):
    """Approves the appraisal (no observations left) and copies its snapshot into the
    ERP's own DB (status -> approved)."""
    migrated = use_case.execute(form_number, user.username)
    return MigratedAppraisalOut(**dataclasses.asdict(migrated))
