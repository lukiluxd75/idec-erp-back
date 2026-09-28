from typing import List

from app.domains.detection.domain.entities.campaign import Campaign
from app.domains.detection.domain.ports.campaign_repository_port import CampaignRepositoryPort


class ListCampaignsUseCase:
    """Active campaigns for the detection start screen's campaign picker."""

    def __init__(self, repository: CampaignRepositoryPort):
        self._repository = repository

    def execute(self) -> List[Campaign]:
        return self._repository.list_active()
