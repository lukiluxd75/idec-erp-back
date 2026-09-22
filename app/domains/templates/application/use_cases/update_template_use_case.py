from typing import Any, Dict

from app.domains.templates.domain.entities.template import Template
from app.domains.templates.domain.exceptions import TemplateNotFoundException
from app.domains.templates.domain.ports.template_repository_port import TemplateRepositoryPort


class UpdateTemplateUseCase:
    """Use case: edit a template's editable fields. Bumps `version` (see
    SqlTemplateRepository.update) so every content change is traceable."""

    def __init__(self, repository: TemplateRepositoryPort):
        self._repository = repository

    def execute(self, template_id: int, changes: Dict[str, Any], user_sub: str) -> Template:
        template = self._repository.update(template_id, changes, user_sub=user_sub)
        if template is None:
            raise TemplateNotFoundException(f"No existe la plantilla {template_id}.")
        return template
