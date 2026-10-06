"""Postgres adapter for AffectedParcelReviewPort — the architect's
confirm/reject actions on an affected_parcel (see doc/bdd.sql: architect_review).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.domains.detection.domain.entities.architect_review import ArchitectReview
from app.domains.detection.domain.ports.affected_parcel_review_port import AffectedParcelReviewPort
from app.domains.detection.infrastructure.models import (
    AffectedParcelModel,
    ArchitectReviewModel,
    DetectionModel,
    ProcessedSectorModel,
    ProcessingRunModel,
)
from app.domains.detection.infrastructure.user_lookup import resolve_user_id

# architect_review.action -> affected_parcel.validation_status.
_ACTION_TO_VALIDATION_STATUS = {
    "confirm": "confirmed",
    "reject": "rejected",
}

# processed_sector statuses a fully-reviewed sector can complete from.
_COMPLETABLE_STATUSES = {"awaiting_validation", "awaiting_manual_alignment"}


def _review_to_entity(row: ArchitectReviewModel) -> ArchitectReview:
    return ArchitectReview(
        id=row.id,
        affected_parcel_id=row.affected_parcel_id,
        action=row.action,
        comment=row.comment,
        created_at=row.created_at,
    )


class SqlAffectedParcelReviewRepository(AffectedParcelReviewPort):
    def __init__(self, db: Session):
        self._db = db

    def _get_parcel(self, affected_parcel_id: int) -> AffectedParcelModel:
        parcel = self._db.query(AffectedParcelModel).filter(
            AffectedParcelModel.id == affected_parcel_id
        ).first()
        if parcel is None:
            raise ValueError(f"affected_parcel {affected_parcel_id} not found")
        return parcel

    def _maybe_complete_sector(self, processed_sector_id: int) -> None:
        sector = self._db.query(ProcessedSectorModel).filter(
            ProcessedSectorModel.id == processed_sector_id
        ).first()
        if sector is None or sector.status not in _COMPLETABLE_STATUSES:
            return
        query = self._db.query(AffectedParcelModel).filter(
            AffectedParcelModel.processed_sector_id == processed_sector_id,
            AffectedParcelModel.validation_status == "pending",
        )
        latest_run = (
            self._db.query(ProcessingRunModel)
            .filter(ProcessingRunModel.processed_sector_id == processed_sector_id)
            .order_by(ProcessingRunModel.id.desc())
            .first()
        )
        if latest_run is not None:
            query = query.join(
                DetectionModel, DetectionModel.id == AffectedParcelModel.detection_id
            ).filter(DetectionModel.processing_run_id == latest_run.id)
        still_pending = query.count()
        if still_pending == 0:
            sector.status = "completed"
            sector.updated_at = datetime.utcnow()

    def review(
        self,
        affected_parcel_id: int,
        action: str,
        comment: Optional[str] = None,
        construction_type: Optional[str] = None,
        created_by_sub: Optional[str] = None,
    ) -> ArchitectReview:
        parcel = self._get_parcel(affected_parcel_id)
        user_id = resolve_user_id(self._db, created_by_sub)

        review_row = ArchitectReviewModel(
            affected_parcel_id=affected_parcel_id,
            action=action,
            comment=comment,
            created_by=user_id,
        )
        self._db.add(review_row)

        new_status = _ACTION_TO_VALIDATION_STATUS.get(action)
        if new_status:
            parcel.validation_status = new_status
            parcel.validated_by = user_id
            parcel.validated_at = datetime.utcnow()
            parcel.updated_at = datetime.utcnow()
        if action == "confirm":
            parcel.construction_type = construction_type

        self._db.flush()
        self._maybe_complete_sector(parcel.processed_sector_id)
        self._db.commit()
        self._db.refresh(review_row)
        return _review_to_entity(review_row)
