from typing import List

from app.domains.templates.domain.entities.variable import Variable
from app.domains.templates.domain.ports.variable_repository_port import VariableRepositoryPort


class ListVariablesUseCase:
    """Use case: list every registered variable (placeholder catalog)."""

    def __init__(self, repository: VariableRepositoryPort):
        self._repository = repository

    def execute(self) -> List[Variable]:
        return self._repository.list()
