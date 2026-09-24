from typing import Optional

from app.domains.templates.domain.entities.template import Template
from app.domains.templates.domain.ports.template_repository_port import TemplateRepositoryPort


class CreateTemplateUseCase:
    """Use case: register a new dynamic template. Starts at version 1, activa=True
    (see Template defaults)."""

    def __init__(self, repository: TemplateRepositoryPort):
        self._repository = repository

    def execute(
        self,
        nombre: str,
        codigo: str,
        area: str,
        tipo_documento: str,
        contenido_html: str,
        descripcion: Optional[str],
        user_sub: str,
    ) -> Template:
        template = Template(
            id=None,
            nombre=nombre,
            codigo=codigo,
            area=area,
            tipo_documento=tipo_documento,
            contenido_html=contenido_html,
            descripcion=descripcion,
        )
        return self._repository.create(template, user_sub=user_sub)
