"""Implements ReviewPort against the ERP's own DB (schema appraisal_review) — the
normal ERP session (get_db), not the operativo one.
"""
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.appraisal_review.domain.entities import ObservationBatch
from app.domains.appraisal_review.domain.ports.review_port import ReviewPort
from app.domains.appraisal_review.infrastructure.models import ObservationBatchModel


class SqlReviewRepository(ReviewPort):
    def __init__(self, db: Session):
        self._db = db

    def save_observations(
        self,
        form_number: str,
        operativo_appraisal_id: UUID,
        observations: list[str],
        reviewed_by: str,
    ) -> ObservationBatch:
        row = ObservationBatchModel(
            form_number=form_number,
            operativo_appraisal_id=operativo_appraisal_id,
            observations=observations,
            reviewed_by=reviewed_by,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)

        return ObservationBatch(
            id=row.id,
            form_number=row.form_number,
            operativo_appraisal_id=row.operativo_appraisal_id,
            observations=row.observations,
            reviewed_by=row.reviewed_by,
            reviewed_at=row.reviewed_at,
        )
