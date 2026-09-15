from typing import Tuple

from app.domains.resolutions.domain.exceptions import PageNotFoundException
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort


class GetPageUseCase:
    """Use case: get the image bytes of a scanned page."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(self, resolution_id: str, order_index: int, user_sub: str) -> Tuple[bytes, str]:
        page = self._repository.get_page(resolution_id, order_index, user_sub)
        if page is None:
            raise PageNotFoundException(
                f"La resolución '{resolution_id}' no tiene una página N° {order_index}."
            )
        return page
