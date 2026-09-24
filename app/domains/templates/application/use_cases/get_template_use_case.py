from app.domains.templates.domain.entities.template import Template
from app.domains.templates.domain.exceptions import TemplateNotFoundException
from app.domains.templates.domain.ports.template_repository_port import TemplateRepositoryPort


class GetTemplateUseCase:
    """Use case: fetch one template's full detail (including contenido_html)."""

    def __init__(self, repository: TemplateRepositoryPort):
        self._repository = repository

    def execute(self, template_id: int) -> Template:
        template = self._repository.get(template_id)
        if template is None:
            raise TemplateNotFoundException(f"No existe la plantilla {template_id}.")
        return template
