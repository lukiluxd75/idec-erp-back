from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from app.domains.resolutions.domain.entities.resolution import Resolution


class ResolutionRepositoryPort(ABC):
    """
    Port that Resolutions infrastructure must implement (see CLAUDE.md §3).
    application/ only knows this interface, never SQLAlchemy or the real DB schema.

    Each resolution belongs to a user (`user_sub`, the Keycloak `sub` of whoever
    uploaded it from the mobile app): every method that reads/writes a specific
    resolution takes `user_sub` and only operates on that user's resolutions —
    so "Mis resoluciones" on the frontend cannot see or touch another person's.
    """

    @abstractmethod
    def list(self, user_sub: str) -> List[Resolution]:
        """The user's (non-deleted) resolutions, newest first."""

    @abstractmethod
    def get(self, resolution_id: str, user_sub: str) -> Optional[Resolution]:
        """Detail of one of the user's resolutions, or None if missing / not theirs."""

    @abstractmethod
    def get_page(self, resolution_id: str, order_index: int, user_sub: str) -> Optional[Tuple[bytes, str]]:
        """Image bytes + mime of a page, or None if missing / not the user's."""

    @abstractmethod
    def create(
        self,
        name: str,
        resolution_number: str,
        pages: List[Tuple[bytes, str]],
        user_sub: str,
    ) -> Resolution:
        """Create a new resolution for the user with its pages (bytes + mime, in order)."""

    @abstractmethod
    def save_table(
        self, resolution_id: str, table_data: Dict[str, Any], status: str, user_sub: str
    ) -> Optional[Resolution]:
        """Update the table (opaque JSON) and status. None if missing / not the user's."""

    @abstractmethod
    def delete(self, resolution_id: str, user_sub: str) -> bool:
        """Soft-delete one of the user's resolutions. True if it existed and was theirs."""
