"""Implements MigratedAppraisalPort against the ERP's own DB (schema appraisal_review)."""
import dataclasses
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.domains.appraisal_review.domain.entities import AppraisalDetail, MigratedAppraisal
from app.domains.appraisal_review.domain.ports.migrated_appraisal_port import MigratedAppraisalPort
from app.domains.appraisal_review.infrastructure.models import MigratedAppraisalModel


def _json_safe(value):
    """Recursively converts dataclasses/Decimal/UUID/date into JSONB-friendly values."""
    if dataclasses.is_dataclass(value):
        return {k: _json_safe(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _owner_name(detail: AppraisalDetail) -> str | None:
    if detail.owner is None:
        return None
    if detail.owner.legal_name:
        return detail.owner.legal_name
    parts = [detail.owner.first_name, detail.owner.last_name_1, detail.owner.last_name_2]
    name = " ".join(p for p in parts if p)
    return name or None


class SqlMigratedAppraisalRepository(MigratedAppraisalPort):
    def __init__(self, db: Session):
        self._db = db

    def save_migration(
        self,
        detail: AppraisalDetail,
        operativo_appraisal_id: UUID,
        migrated_by: str,
    ) -> MigratedAppraisal:
        now = datetime.now(timezone.utc)

        self._db.execute(
            update(MigratedAppraisalModel)
            .where(
                MigratedAppraisalModel.form_number == detail.form_number,
                MigratedAppraisalModel.is_active.is_(True),
            )
            .values(is_active=False, superseded_at=now)
        )

        row = MigratedAppraisalModel(
            form_number=detail.form_number,
            operativo_appraisal_id=operativo_appraisal_id,
            is_active=True,
            fiscal_year=detail.fiscal_year,
            address=detail.property.address if detail.property else None,
            cadastral_code=detail.property.cadastral_code if detail.property else None,
            owner_name=_owner_name(detail),
            owner_document=detail.owner.document_number if detail.owner else None,
            land_area=detail.land_area,
            blocks_area=detail.blocks_area,
            improvements_area=detail.improvements_area,
            total_value=detail.total_value,
            snapshot_json=_json_safe(detail),
            migrated_by=migrated_by,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)

        return MigratedAppraisal(
            id=row.id,
            form_number=row.form_number,
            operativo_appraisal_id=row.operativo_appraisal_id,
            is_active=row.is_active,
            migrated_by=row.migrated_by,
            migrated_at=row.migrated_at,
        )
