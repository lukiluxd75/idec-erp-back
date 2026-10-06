"""Postgres adapter for CampaignRepositoryPort against `detection_results.campaign`."""
from datetime import date
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.detection.domain.entities.campaign import Campaign
from app.domains.detection.domain.exceptions import CampaignCodeAlreadyExists
from app.domains.detection.domain.ports.campaign_repository_port import CampaignRepositoryPort
from app.domains.detection.infrastructure.models import CampaignModel
from app.domains.detection.infrastructure.user_lookup import resolve_user_id


def _to_entity(row: CampaignModel) -> Campaign:
    return Campaign(
        id=row.id,
        code=row.code,
        name=row.name,
        status=row.status,
        n_sectors=row.n_sectors,
        n_affected_parcels=row.n_affected_parcels,
        description=row.description,
        year_a=row.year_a,
        year_b=row.year_b,
        period_start=row.period_start,
        period_end=row.period_end,
        created_at=row.created_at,
        closed_at=row.closed_at,
    )


class SqlCampaignRepository(CampaignRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def list_active(self) -> List[Campaign]:
        rows = (
            self._db.query(CampaignModel)
            .filter(CampaignModel.status == "active")
            .order_by(CampaignModel.created_at.desc())
            .all()
        )
        return [_to_entity(r) for r in rows]

    def create(
        self,
        code: str,
        name: str,
        year_a: int,
        year_b: int,
        description: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        created_by_sub: Optional[str] = None,
    ) -> Campaign:
        campaign = CampaignModel(
            code=code,
            name=name,
            year_a=year_a,
            year_b=year_b,
            description=description,
            period_start=period_start,
            period_end=period_end,
            created_by=resolve_user_id(self._db, created_by_sub),
        )
        self._db.add(campaign)
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise CampaignCodeAlreadyExists(code) from exc
        self._db.refresh(campaign)
        return _to_entity(campaign)
