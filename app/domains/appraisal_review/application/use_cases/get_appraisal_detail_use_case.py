from app.domains.appraisal_review.domain.entities import AppraisalDetail
from app.domains.appraisal_review.domain.exceptions import AppraisalNotFoundException
from app.domains.appraisal_review.domain.ports import OperativoAppraisalPort


class GetAppraisalDetailUseCase:
    def __init__(self, operativo_repo: OperativoAppraisalPort):
        self._operativo_repo = operativo_repo

    def execute(self, form_number: str) -> AppraisalDetail:
        detail = self._operativo_repo.get_by_form_number(form_number)
        if detail is None:
            raise AppraisalNotFoundException(f"No existe un formulario de Avalúos con número '{form_number}'")
        return detail
