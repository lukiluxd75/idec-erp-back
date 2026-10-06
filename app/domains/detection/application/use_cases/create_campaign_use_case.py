from datetime import date
from typing import Optional

from app.domains.detection.domain.entities.campaign import Campaign
from app.domains.detection.domain.ports.campaign_repository_port import CampaignRepositoryPort


class CreateCampaignUseCase:
    """Backs the "+ Nueva campaña" quick-create on the detection start screen
    -- created ready to use (status defaults to 'active', see CampaignRepositoryPort)."""

    def __init__(self, repository: CampaignRepositoryPort):
        self._repository = repository

    def execute(
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
        return self._repository.create(
            code=code,
            name=name,
            year_a=year_a,
            year_b=year_b,
            description=description,
            period_start=period_start,
            period_end=period_end,
            created_by_sub=created_by_sub,
        )
