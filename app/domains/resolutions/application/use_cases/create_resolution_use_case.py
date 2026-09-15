from typing import List, Tuple

from app.domains.resolutions.domain.entities.resolution import Resolution
from app.domains.resolutions.domain.exceptions import ResolutionWithoutPagesException
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort


class CreateResolutionUseCase:
    """Use case: register a newly scanned resolution (from the mobile app)
    together with its page photos, in order. Starts in status 'pendiente_ocr':
    the surface-table OCR has not run yet."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(
        self, name: str, resolution_number: str, pages: List[Tuple[bytes, str]], user_sub: str
    ) -> Resolution:
        if not pages:
            raise ResolutionWithoutPagesException(
                "Hay que adjuntar al menos una foto de página para crear la resolución."
            )
        return self._repository.create(
            name=name, resolution_number=resolution_number, pages=pages, user_sub=user_sub
        )
