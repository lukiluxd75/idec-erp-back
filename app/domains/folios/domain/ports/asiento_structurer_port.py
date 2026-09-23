from abc import ABC, abstractmethod
from typing import Any, Dict


class AsientoStructurerPort(ABC):
    """Optional LLM pass over ONE asiento of column A, used only when the
    rule-based parser left gaps (no people or no act found). The adapter is
    Ollama (infrastructure/ollama_asiento_structurer.py); `is_configured()` False
    simply skips the step. Implementations raise
    AsientoStructurerUnavailableException on any failure -- never fatal."""

    @abstractmethod
    def is_configured(self) -> bool:
        """False when no LLM host is set -- the pipeline then skips this pass."""

    @abstractmethod
    def structure(self, raw_text: str) -> Dict[str, Any]:
        """JSON with keys: personas[{nombre, estado_civil, ci, proporcion}], acto,
        documento, autoridad. Unvalidated -- the caller cross-checks it against
        raw_text before trusting it."""
