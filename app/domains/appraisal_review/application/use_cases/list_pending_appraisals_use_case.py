from app.domains.appraisal_review.domain.entities import AppraisalSummary
from app.domains.appraisal_review.domain.ports import OperativoAppraisalPort


class ListPendingAppraisalsUseCase:
    def __init__(self, operativo_repo: OperativoAppraisalPort):
        self._operativo_repo = operativo_repo

    def execute(self) -> list[AppraisalSummary]:
        return self._operativo_repo.list_pending_review()
