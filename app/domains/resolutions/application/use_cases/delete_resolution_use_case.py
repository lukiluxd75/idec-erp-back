from app.domains.resolutions.domain.exceptions import ResolutionNotFoundException
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort


class DeleteResolutionUseCase:
    """Use case: soft-delete one of the user's resolutions."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(self, resolution_id: str, user_sub: str) -> None:
        existed = self._repository.delete(resolution_id, user_sub)
        if not existed:
            raise ResolutionNotFoundException(f"No existe la resolución '{resolution_id}'.")
