from typing import List

from app.domains.resolutions.domain.entities.resolution import PlanPage, PlantaStatus
from app.domains.resolutions.domain.exceptions import InvalidPlantaException, PlanPageNotFoundException
from app.domains.resolutions.domain.plantas import PLANTAS_RESUMEN
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort


class SetPlanPagePlantasUseCase:
    """Use case: assign by hand the planta(s) of a plan page from the web --
    to fix a detection or fill in a page whose title could not be read."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(self, resolution_id: str, order_index: int, plantas: List[str], user_sub: str) -> PlanPage:
        if not plantas:
            raise InvalidPlantaException("Elija al menos una planta.")
        for planta in plantas:
            if planta not in PLANTAS_RESUMEN:
                raise InvalidPlantaException(f"Planta '{planta}' inválida. Debe ser una de PLANTAS_RESUMEN.")
        page = self._repository.update_plan_page_planta(
            resolution_id,
            order_index,
            [p for p in PLANTAS_RESUMEN if p in plantas],
            PlantaStatus.MANUAL,
            user_sub=user_sub,
        )
        if page is None:
            raise PlanPageNotFoundException(
                f"La resolución '{resolution_id}' no tiene una página de plano N° {order_index}."
            )
        return page


class RequestPlantaDetectionUseCase:
    """Use case: ask again for the planta of a plan page to be read from its
    title (e.g. after an OCR error). Marks it DETECTANDO; the endpoint then
    runs DetectPlanPagePlantaUseCase in background."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(self, resolution_id: str, order_index: int, user_sub: str) -> PlanPage:
        page = self._repository.update_plan_page_planta(
            resolution_id, order_index, [], PlantaStatus.DETECTANDO, user_sub=user_sub
        )
        if page is None:
            raise PlanPageNotFoundException(
                f"La resolución '{resolution_id}' no tiene una página de plano N° {order_index}."
            )
        return page
