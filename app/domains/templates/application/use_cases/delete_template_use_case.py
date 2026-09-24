from app.domains.templates.domain.entities.template import Template
from app.domains.templates.domain.exceptions import TemplateNotFoundException
from app.domains.templates.domain.ports.template_repository_port import TemplateRepositoryPort


class DeleteTemplateUseCase:
    """Use case: deactivate a template (soft delete -- see `activa` column; there is
    no hard delete because documento_generado rows may reference the template)."""

    def __init__(self, repository: TemplateRepositoryPort):
        self._repository = repository

    def execute(self, template_id: int, user_sub: str) -> Template:
        template = self._repository.set_active(template_id, activa=False, user_sub=user_sub)
        if template is None:
            raise TemplateNotFoundException(f"No existe la plantilla {template_id}.")
        return template
