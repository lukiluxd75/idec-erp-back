from app.domains.appraisal_review.domain.entities import MigratedAppraisal
from app.domains.appraisal_review.domain.exceptions import AppraisalNotFoundException
from app.domains.appraisal_review.domain.ports import MigratedAppraisalPort, OperativoAppraisalPort


class MigrateAppraisalUseCase:
    """Copies the appraisal (unmodified — the reviewer never edits data) into the ERP's
    own DB and marks it 'approved' in catastro_operativo. Only meant to run when the
    review found nothing to send back as an observation.
    """

    def __init__(self, operativo_repo: OperativoAppraisalPort, migrated_repo: MigratedAppraisalPort):
        self._operativo_repo = operativo_repo
        self._migrated_repo = migrated_repo

    def execute(self, form_number: str, migrated_by: str) -> MigratedAppraisal:
        detail = self._operativo_repo.get_by_form_number(form_number)
        if detail is None:
            raise AppraisalNotFoundException(f"No existe un formulario de Avalúos con número '{form_number}'")

        migrated = self._migrated_repo.save_migration(detail, detail.id, migrated_by)
        self._operativo_repo.mark_approved(detail.id)
        return migrated
