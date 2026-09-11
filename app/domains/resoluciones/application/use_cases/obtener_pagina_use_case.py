from typing import Tuple

from app.domains.resoluciones.domain.exceptions import PaginaNoEncontradaException
from app.domains.resoluciones.domain.ports.resolucion_repository_port import ResolucionRepositoryPort


class ObtenerPaginaUseCase:
    """Caso de uso: obtener los bytes de imagen de una página escaneada."""

    def __init__(self, repository: ResolucionRepositoryPort):
        self._repository = repository

    def execute(self, id_resolucion: str, orden: int, user_sub: str) -> Tuple[bytes, str]:
        pagina = self._repository.obtener_pagina(id_resolucion, orden, user_sub)
        if pagina is None:
            raise PaginaNoEncontradaException(
                f"La resolución '{id_resolucion}' no tiene una página N° {orden}."
            )
        return pagina
