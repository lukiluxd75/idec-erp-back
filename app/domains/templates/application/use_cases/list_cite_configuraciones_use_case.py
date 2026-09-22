from typing import List

from app.domains.templates.domain.entities.cite import CiteConfiguracion
from app.domains.templates.domain.ports.cite_repository_port import CiteRepositoryPort


class ListCiteConfiguracionesUseCase:
    """Use case: list every registered CITE sigla (area + tipo_documento)."""

    def __init__(self, repository: CiteRepositoryPort):
        self._repository = repository

    def execute(self) -> List[CiteConfiguracion]:
        return self._repository.list_configuraciones()
