from typing import List, Tuple

from app.core.errors.exceptions import DomainException
from app.domains.resolutions.domain.entities.resolution import PlantaStatus, Resolution
from app.domains.resolutions.domain.exceptions import (
    InvalidPlantaException,
    NoPlanPagesException,
    ResolutionNotFoundException,
)
from app.domains.resolutions.domain.plantas import PLANTAS_RESUMEN
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort

VALID_SOURCES = ("app", "web")


class AddPlanPagesUseCase:
    """Use case: attach one or more floor-plan photos to a resolution. Each
    one comes with the planta(s) it shows -- several for a sheet that is valid
    for several identical floors ("PLANTA TIPO 2° - 4° PISO") -- or with NONE,
    and then its planta is read later from the plan title (see
    DetectPlanPagePlantaUseCase). Same use case for both channels — the mobile
    app and the web upload hit the exact same endpoint (see `source`, just
    metadata about who called it, no different validation)."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(
        self,
        resolution_id: str,
        pages: List[Tuple[bytes, str, List[str]]],
        source: str,
        user_sub: str,
    ) -> Tuple[Resolution, List[int]]:
        """Returns the resolution and the order_index of the pages whose
        planta still has to be detected."""
        if not pages:
            raise NoPlanPagesException("Hay que adjuntar al menos una foto del plano.")
        if source not in VALID_SOURCES:
            raise DomainException(
                f"Origen '{source}' inválido. Debe ser uno de: {', '.join(VALID_SOURCES)}."
            )
        limpias = []
        for content, mime, plantas in pages:
            for planta in plantas:
                if planta not in PLANTAS_RESUMEN:
                    raise InvalidPlantaException(
                        f"Planta '{planta}' inválida. Debe ser una de PLANTAS_RESUMEN."
                    )
            # Sin repetidas y en el orden de PLANTAS_RESUMEN (sótano, baja, 1º piso...).
            limpias.append((content, mime, [p for p in PLANTAS_RESUMEN if p in plantas]))

        antes = self._repository.get(resolution_id, user_sub)
        resolution = self._repository.add_plan_pages(resolution_id, limpias, source, user_sub)
        if resolution is None:
            raise ResolutionNotFoundException(f"No existe la resolución '{resolution_id}'.")
        ya_estaban = {p.order_index for p in (antes.plan_pages if antes else [])}
        pendientes = [
            p.order_index
            for p in resolution.plan_pages
            if p.order_index not in ya_estaban and p.planta_status == PlantaStatus.DETECTANDO
        ]
        return resolution, pendientes
