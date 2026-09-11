from typing import List, Tuple

from app.domains.resoluciones.domain.entities.resolucion import Resolucion
from app.domains.resoluciones.domain.exceptions import ResolucionSinPaginasException
from app.domains.resoluciones.domain.ports.resolucion_repository_port import ResolucionRepositoryPort


class CrearResolucionUseCase:
    """Caso de uso: registrar una resolución recién escaneada (desde la app móvil)
    junto con las fotos de sus páginas, en orden. Arranca en estado 'pendiente_ocr':
    todavía no se corrió el OCR de la tabla de superficies."""

    def __init__(self, repository: ResolucionRepositoryPort):
        self._repository = repository

    def execute(
        self, nombre: str, nro_resolucion: str, paginas: List[Tuple[bytes, str]], user_sub: str
    ) -> Resolucion:
        if not paginas:
            raise ResolucionSinPaginasException(
                "Hay que adjuntar al menos una foto de página para crear la resolución."
            )
        return self._repository.crear(
            nombre=nombre, nro_resolucion=nro_resolucion, paginas=paginas, user_sub=user_sub
        )
