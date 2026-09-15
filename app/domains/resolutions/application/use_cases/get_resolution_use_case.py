from app.domains.resolutions.domain.entities.resolution import Resolution
from app.domains.resolutions.domain.exceptions import ResolutionNotFoundException
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort


class GetResolutionUseCase:
    """Use case: get detail (pages + table) of one of the user's resolutions."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(self, resolution_id: str, user_sub: str) -> Resolution:
        resolution = self._repository.get(resolution_id, user_sub)
        if resolution is None:
            raise ResolutionNotFoundException(f"No existe la resolución '{resolution_id}'.")
        return resolution
