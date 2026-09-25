import logging

from app.domains.resolutions.domain.entities.resolution import PlanPage, PlantaStatus
from app.domains.resolutions.domain.exceptions import PlanOcrUnavailableException, PlanPageNotFoundException
from app.domains.resolutions.domain.plan_title import detect_plantas
from app.domains.resolutions.domain.ports.plan_ocr_port import PlanOcrPort
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort

logger = logging.getLogger("uvicorn.error")


class DetectPlanPagePlantaUseCase:
    """Use case (background): read the title of a plan page with OCR
    ("PLANTA TIPO 2° - 4° PISO") and assign its planta(s). If there is no clear
    title the page stays SIN_TITULO -- it never guesses -- and if the OCR
    fails, ERROR; in both cases the web lets the user pick it by hand."""

    def __init__(self, repository: ResolutionRepositoryPort, ocr: PlanOcrPort):
        self._repository = repository
        self._ocr = ocr

    def execute(self, resolution_id: str, order_index: int) -> PlanPage:
        imagen = self._repository.get_plan_page_for_processing(resolution_id, order_index)
        if imagen is None:
            raise PlanPageNotFoundException(
                f"La resolución '{resolution_id}' no tiene una página de plano N° {order_index}."
            )
        content, _ = imagen
        try:
            bloques = self._ocr.read(content, f"plano_{order_index}.jpg")
        except PlanOcrUnavailableException as exc:
            logger.warning("resolutions: OCR del plano %s/%s falló: %s", resolution_id, order_index, exc)
            return self._repository.update_plan_page_planta(
                resolution_id, order_index, [], PlantaStatus.ERROR, detection={"motivo": str(exc)}
            )

        deteccion = detect_plantas(bloques)
        detalle = {"motivo": deteccion.motivo, "candidatos": deteccion.candidatos, "bloques_ocr": len(bloques)}
        return self._repository.update_plan_page_planta(
            resolution_id,
            order_index,
            deteccion.plantas,
            PlantaStatus.DETECTADA if deteccion.plantas else PlantaStatus.SIN_TITULO,
            title=deteccion.titulo,
            detection=detalle,
        )
