from typing import Any, Dict

from app.domains.templates.domain.exceptions import TemplateNotFoundException
from app.domains.templates.domain.ports.template_repository_port import TemplateRepositoryPort
from app.domains.templates.domain.ports.template_engine_port import TemplateEnginePort

class PreviewDocumentUseCase:
    """
    Obtiene el HTML de una plantilla y lo envía al Motor Externo para renderizarlo,
    devolviendo la vista previa al usuario.
    """
    def __init__(
        self,
        repository: TemplateRepositoryPort,
        engine_client: TemplateEnginePort
    ):
        self._repository = repository
        self._engine_client = engine_client

    def execute(self, template_id: int, variables: Dict[str, Any]) -> str:
        template = self._repository.get(template_id)
        if template is None:
            raise TemplateNotFoundException(f"No existe la plantilla {template_id}.")

        rendered_html = self._engine_client.preview_template(template.contenido_html, variables)
        return rendered_html
