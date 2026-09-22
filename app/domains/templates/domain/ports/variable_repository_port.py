from abc import ABC, abstractmethod
from typing import List, Optional

from app.domains.templates.domain.entities.variable import Variable


class VariableRepositoryPort(ABC):
    """Port that Templates infrastructure must implement for Variable (see CLAUDE.md §3)."""

    @abstractmethod
    def list(self) -> List[Variable]:
        """Every registered variable (active and inactive), by name."""

    @abstractmethod
    def get_by_clave(self, clave: str) -> Optional[Variable]:
        """Lookup by the unique key."""

    @abstractmethod
    def create(self, variable: Variable) -> Variable:
        """Create a new variable."""
