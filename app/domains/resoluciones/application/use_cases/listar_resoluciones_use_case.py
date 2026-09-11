from typing import List

from app.domains.resoluciones.domain.entities.resolucion import Resolucion
from app.domains.resoluciones.domain.ports.resolucion_repository_port import ResolucionRepositoryPort


class ListarResolucionesUseCase:
    """Caso de uso: listar las resoluciones del usuario autenticado ('Mis resoluciones')."""

    def __init__(self, repository: ResolucionRepositoryPort):
        self._repository = repository

    def execute(self, user_sub: str) -> List[Resolucion]:
        return self._repository.listar(user_sub)
