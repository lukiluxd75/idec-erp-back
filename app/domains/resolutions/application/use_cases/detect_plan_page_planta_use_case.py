import logging

from app.domains.resolutions.domain.entities.resolution import PlanPage, PlantaStatus
from app.domains.resolutions.domain.exceptions import PlanOcrUnavailableException, PlanPageNotFoundException
from app.domains.resolutions.domain.plan_tiles import LADOS, mosaicos, recortes_de_titulo, variantes_de_recorte
from app.domains.resolutions.domain.plan_title import (
    TitleBlock,
    detect_plantas,
    parece_escala,
    parece_trozo_de_titulo,
)
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
        if not deteccion.plantas:
            # Plano grande/alargado: el título puede no leerse en la página entera.
            # Se reintenta por mosaicos, cada vez mas chicos, y se detecta sobre
            # TODOS los bloques juntos (la regla "el título es lo más grande"
            # necesita verlos a la vez).
            try:
                for lado in LADOS:
                    bloques = bloques + self._leer_mosaicos(content, order_index, lado)
                    deteccion = detect_plantas(bloques)
                    if deteccion.plantas:
                        break
                if not deteccion.plantas:
                    # Los mosaicos pueden partir el título en el borde ("PLANTA 6" /
                    # "6°PIS0"): se relee una ventana alrededor de cada trozo.
                    bloques = bloques + self._releer_trozos(content, order_index, bloques)
                    deteccion = detect_plantas(bloques)
            except PlanOcrUnavailableException as exc:
                logger.warning("resolutions: OCR por mosaicos del plano %s/%s falló: %s", resolution_id, order_index, exc)
        detalle = {"motivo": deteccion.motivo, "candidatos": deteccion.candidatos, "bloques_ocr": len(bloques)}
        return self._repository.update_plan_page_planta(
            resolution_id,
            order_index,
            deteccion.plantas,
            PlantaStatus.DETECTADA if deteccion.plantas else PlantaStatus.SIN_TITULO,
            title=deteccion.titulo,
            detection=detalle,
        )

    def _leer_mosaicos(self, content: bytes, order_index: int, lado: int) -> list:
        bloques = []
        for n, (jpg, x0, y0) in enumerate(mosaicos(content, lado)):
            for b in self._ocr.read(jpg, f"plano_{order_index}_m{n}.jpg"):
                bloques.append(TitleBlock(b.text, b.x0 + x0, b.y0 + y0, b.x1 + x0, b.y1 + y0))
        return bloques

    def _releer_trozos(self, content: bytes, order_index: int, bloques: list) -> list:
        anclas = [(b.x0, b.y0, b.x1, b.y1) for b in bloques if parece_trozo_de_titulo(b.text)]
        # El título va justo encima de la escala: se relee la zona de arriba de cada "ESC.1/100".
        for b in bloques:
            if parece_escala(b.text):
                alto = max(b.y1 - b.y0, 20)
                anclas.append((b.x0, b.y0 - 3 * alto, b.x1, b.y1))
        nuevos = []
        for n, (jpg, x0, y0) in enumerate(recortes_de_titulo(content, anclas)):
            # El OCR lee distinto cada versión del recorte: se prueban hasta que sale el título.
            for v, (variante, escala) in enumerate(variantes_de_recorte(jpg)):
                for b in self._ocr.read(variante, f"plano_{order_index}_r{n}v{v}.jpg"):
                    nuevos.append(
                        TitleBlock(b.text, b.x0 / escala + x0, b.y0 / escala + y0, b.x1 / escala + x0, b.y1 / escala + y0)
                    )
                if detect_plantas(bloques + nuevos).plantas:
                    return nuevos
        return nuevos
