from app.domains.appraisal_review.domain.entities import AppraisalSummary
from app.domains.appraisal_review.domain.ports import OperativoAppraisalPort


class SearchAppraisalsUseCase:
    """Looks up appraisals by form_number regardless of status — lets the reviewer pull
    up a specific form directly (e.g. one Avalúos hasn't marked 'submitted' yet, since
    that system has its own separate login and there is no automatic push to the ERP).
    """

    def __init__(self, operativo_repo: OperativoAppraisalPort):
        self._operativo_repo = operativo_repo

    def execute(self, term: str, limit: int = 40) -> list[AppraisalSummary]:
        term = (term or "").strip()
        if len(term) < 2:
            return []
        return self._operativo_repo.search_by_form_number(term, limit)
