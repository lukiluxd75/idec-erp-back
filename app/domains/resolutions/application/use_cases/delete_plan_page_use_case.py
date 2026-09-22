from app.domains.resolutions.domain.entities.resolution import Resolution
from app.domains.resolutions.domain.exceptions import PlanPageNotFoundException
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort


class DeletePlanPageUseCase:
    """Use case: remove one floor-plan page — mainly for the web upload UI,
    to correct a page that was tagged with the wrong planta or is unusable."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(self, resolution_id: str, order_index: int, user_sub: str) -> Resolution:
        resolution = self._repository.delete_plan_page(resolution_id, order_index, user_sub)
        if resolution is None:
            raise PlanPageNotFoundException(
                f"La resolución '{resolution_id}' no tiene una página de plano N° {order_index}."
            )
        return resolution
