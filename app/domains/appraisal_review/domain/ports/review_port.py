"""Write port for the ERP's own review history — the observations sent back to Avalúos."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domains.appraisal_review.domain.entities import ObservationBatch


class ReviewPort(ABC):

    @abstractmethod
    def save_observations(
        self,
        form_number: str,
        operativo_appraisal_id: UUID,
        observations: list[str],
        reviewed_by: str,
    ) -> ObservationBatch:
        """Logs one review cycle's point-by-point observations."""
