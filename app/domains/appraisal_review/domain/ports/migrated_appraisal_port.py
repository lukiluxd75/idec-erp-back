"""Write port for the ERP's own copy of appraisals approved with no observations left."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domains.appraisal_review.domain.entities import AppraisalDetail, MigratedAppraisal


class MigratedAppraisalPort(ABC):

    @abstractmethod
    def save_migration(
        self,
        detail: AppraisalDetail,
        operativo_appraisal_id: UUID,
        migrated_by: str,
    ) -> MigratedAppraisal:
        """Deactivates the previous active migration for this form_number (if any) and
        inserts a new row with the current snapshot — re-migration without losing history."""
