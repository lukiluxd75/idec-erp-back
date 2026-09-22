from typing import List

from app.domains.templates.domain.entities.template import Template
from app.domains.templates.domain.ports.template_repository_port import TemplateRepositoryPort


class ListTemplatesUseCase:
    """Use case: list every registered template (catalog view)."""

    def __init__(self, repository: TemplateRepositoryPort):
        self._repository = repository

    def execute(self) -> List[Template]:
        return self._repository.list()
