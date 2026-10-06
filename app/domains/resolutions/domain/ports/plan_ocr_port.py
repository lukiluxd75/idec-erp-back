from abc import ABC, abstractmethod
from typing import List

from app.domains.resolutions.domain.plan_title import TitleBlock


class PlanOcrPort(ABC):
    """Reads the text of a plan page (to find its title and so its planta).
    Raises PlanOcrUnavailableException if the OCR service fails."""

    @abstractmethod
    def read(self, image_bytes: bytes, filename: str = "plano.jpg") -> List[TitleBlock]:
        ...
