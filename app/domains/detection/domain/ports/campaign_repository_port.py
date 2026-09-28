from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional

from app.domains.detection.domain.entities.campaign import Campaign


class CampaignRepositoryPort(ABC):
    """Port the `detection` infrastructure must implement (see CLAUDE.md §3)
    for `detection_results.campaign` — the period (e.g. a quarter) a
    processed_sector optionally belongs to."""

    @abstractmethod
    def list_active(self) -> List[Campaign]:
        """Active campaigns, newest first — for the campaign picker."""

    @abstractmethod
    def create(
        self,
        code: str,
        name: str,
        description: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        created_by_sub: Optional[str] = None,
    ) -> Campaign:
        """Create a new campaign (status defaults to 'active' -- created
        ready to use, see the frontend's "+ Nueva campaña" quick-create)."""
