from typing import List, Tuple

from app.core.errors.exceptions import DomainException
from app.domains.resolutions.domain.entities.resolution import Resolution
from app.domains.resolutions.domain.exceptions import (
    InvalidPlantaException,
    NoPlanPagesException,
    ResolutionNotFoundException,
)
from app.domains.resolutions.domain.plantas import PLANTAS_RESUMEN
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort

VALID_SOURCES = ("app", "web")


class AddPlanPagesUseCase:
    """Use case: attach one or more floor-plan photos to a resolution, each
    tagged with which planta it shows. Same use case for both channels — the
    mobile app and the web upload hit the exact same endpoint (see
    `source`, just metadata about who called it, no different validation)."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(
        self,
        resolution_id: str,
        pages: List[Tuple[bytes, str, str]],
        source: str,
        user_sub: str,
    ) -> Resolution:
        if not pages:
            raise NoPlanPagesException("Hay que adjuntar al menos una foto del plano.")
        if source not in VALID_SOURCES:
            raise DomainException(
                f"Origen '{source}' inválido. Debe ser uno de: {', '.join(VALID_SOURCES)}."
            )
        for _, _, planta in pages:
            if planta not in PLANTAS_RESUMEN:
                raise InvalidPlantaException(
                    f"Planta '{planta}' inválida. Debe ser una de PLANTAS_RESUMEN."
                )

        resolution = self._repository.add_plan_pages(resolution_id, pages, source, user_sub)
        if resolution is None:
            raise ResolutionNotFoundException(f"No existe la resolución '{resolution_id}'.")
        return resolution
