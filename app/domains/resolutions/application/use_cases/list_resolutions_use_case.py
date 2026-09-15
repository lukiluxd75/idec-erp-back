from typing import List

from app.domains.resolutions.domain.entities.resolution import Resolution
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort


class ListResolutionsUseCase:
    """Use case: list the authenticated user's resolutions ('Mis resoluciones')."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(self, user_sub: str) -> List[Resolution]:
        return self._repository.list(user_sub)
