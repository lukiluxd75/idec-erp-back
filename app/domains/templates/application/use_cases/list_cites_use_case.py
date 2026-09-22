from typing import List

from app.domains.templates.domain.entities.cite import CiteGenerado
from app.domains.templates.domain.ports.cite_repository_port import CiteRepositoryPort


class ListCitesUseCase:
    """Use case: list every emitted CITE (history view), newest first."""

    def __init__(self, repository: CiteRepositoryPort):
        self._repository = repository

    def execute(self) -> List[CiteGenerado]:
        return self._repository.list_generados()
