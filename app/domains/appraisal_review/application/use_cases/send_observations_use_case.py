from app.domains.appraisal_review.domain.entities import ObservationBatch
from app.domains.appraisal_review.domain.exceptions import AppraisalNotFoundException
from app.domains.appraisal_review.domain.ports import OperativoAppraisalPort, ReviewPort


class SendObservationsUseCase:
    """Sends the appraisal back to Avalúos with observations: logs them in the ERP's own
    DB and flips catastro_operativo's status to 'needs_correction' so the architect sees
    it needs fixing.
    """

    def __init__(self, operativo_repo: OperativoAppraisalPort, review_repo: ReviewPort):
        self._operativo_repo = operativo_repo
        self._review_repo = review_repo

    def execute(self, form_number: str, observations: list[str], reviewed_by: str) -> ObservationBatch:
        detail = self._operativo_repo.get_by_form_number(form_number)
        if detail is None:
            raise AppraisalNotFoundException(f"No existe un formulario de Avalúos con número '{form_number}'")

        batch = self._review_repo.save_observations(form_number, detail.id, observations, reviewed_by)
        self._operativo_repo.mark_needs_correction(detail.id)
        return batch
