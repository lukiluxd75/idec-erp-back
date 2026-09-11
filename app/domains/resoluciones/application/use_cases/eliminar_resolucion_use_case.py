from app.domains.resoluciones.domain.exceptions import ResolucionNoEncontradaException
from app.domains.resoluciones.domain.ports.resolucion_repository_port import ResolucionRepositoryPort


class EliminarResolucionUseCase:
    """Caso de uso: eliminar (soft delete) una resolución del usuario."""

    def __init__(self, repository: ResolucionRepositoryPort):
        self._repository = repository

    def execute(self, id_resolucion: str, user_sub: str) -> None:
        existia = self._repository.eliminar(id_resolucion, user_sub)
        if not existia:
            raise ResolucionNoEncontradaException(f"No existe la resolución '{id_resolucion}'.")
