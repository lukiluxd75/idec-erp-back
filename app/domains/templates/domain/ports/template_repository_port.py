from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domains.templates.domain.entities.template import Template


class TemplateRepositoryPort(ABC):
    """
    Port that Templates infrastructure must implement (see CLAUDE.md §3).
    application/ only knows this interface, never SQLAlchemy or the real DB schema.
    """

    @abstractmethod
    def list(self) -> List[Template]:
        """Every registered template (active and inactive), newest first."""

    @abstractmethod
    def get(self, template_id: int) -> Optional[Template]:
        """Detail of one template, or None if missing."""

    @abstractmethod
    def get_by_codigo(self, codigo: str) -> Optional[Template]:
        """Lookup by the unique business code."""

    @abstractmethod
    def create(self, template: Template, user_sub: str) -> Template:
        """Create a new template."""

    @abstractmethod
    def update(self, template_id: int, changes: Dict[str, Any], user_sub: str) -> Optional[Template]:
        """Apply a partial update (only the given fields). None if missing."""

    @abstractmethod
    def set_active(self, template_id: int, activa: bool, user_sub: str) -> Optional[Template]:
        """Activate/deactivate a template (soft delete). None if missing."""
