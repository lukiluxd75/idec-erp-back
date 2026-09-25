from typing import Any, Dict, Protocol

class TemplateEnginePort(Protocol):
    def render_template(self, html_content: str, variables: Dict[str, Any]) -> str:
        """
        Envía el HTML base y los valores de las variables a la aplicación externa
        para que los combine/compile y retorne el HTML (o PDF) resultante.
        """
        ...

    def preview_template(self, html_content: str, variables: Dict[str, Any]) -> str:
        """
        Igual que render, pero específico para previsualización (podría omitir marcas de agua, etc.).
        """
        ...
