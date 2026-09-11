from typing import Any, Dict

from app.domains.resoluciones.domain.entities.resolucion import ESTADOS_VALIDOS, Resolucion
from app.domains.resoluciones.domain.exceptions import (
    EstadoInvalidoException,
    ResolucionNoEncontradaException,
)
from app.domains.resoluciones.domain.ports.resolucion_repository_port import ResolucionRepositoryPort


class GuardarTablaUseCase:
    """Caso de uso: guardar la tabla de superficies (OCR revisado/editado) y el
    estado del flujo de una resolución — 'Guardar borrador' o 'Generar Excel'."""

    def __init__(self, repository: ResolucionRepositoryPort):
        self._repository = repository

    def execute(self, id_resolucion: str, tabla: Dict[str, Any], estado: str, user_sub: str) -> Resolucion:
        if estado not in ESTADOS_VALIDOS:
            raise EstadoInvalidoException(
                f"Estado '{estado}' inválido. Debe ser uno de: {', '.join(ESTADOS_VALIDOS)}."
            )

        resolucion = self._repository.guardar_tabla(id_resolucion, tabla, estado, user_sub)
        if resolucion is None:
            raise ResolucionNoEncontradaException(f"No existe la resolución '{id_resolucion}'.")
        return resolucion
