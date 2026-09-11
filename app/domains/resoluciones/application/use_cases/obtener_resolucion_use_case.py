from app.domains.resoluciones.domain.entities.resolucion import Resolucion
from app.domains.resoluciones.domain.exceptions import ResolucionNoEncontradaException
from app.domains.resoluciones.domain.ports.resolucion_repository_port import ResolucionRepositoryPort


class ObtenerResolucionUseCase:
    """Caso de uso: obtener el detalle (páginas + tabla) de una resolución del usuario."""

    def __init__(self, repository: ResolucionRepositoryPort):
        self._repository = repository

    def execute(self, id_resolucion: str, user_sub: str) -> Resolucion:
        resolucion = self._repository.obtener(id_resolucion, user_sub)
        if resolucion is None:
            raise ResolucionNoEncontradaException(f"No existe la resolución '{id_resolucion}'.")
        return resolucion
