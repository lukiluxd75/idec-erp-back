from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.domains.geoextraction.domain.entities.capture import Capture


class CaptureStorePort(ABC):
    """
    Port that Geoextraction infrastructure must implement (see CLAUDE.md §3).
    application/ only knows this interface, never how/where the photo is actually
    stored (today: Postgres — see SqlCaptureStore, table `geoextraction_captures`;
    if that needs to change, write another adapter here without touching use cases).
    It started as an in-process memory store, but that broke with multiple workers:
    each process had its own memory, so a capture saved by the worker that handled
    the phone POST was invisible to the worker serving the web GET.

    Each capture belongs to a user (`user_sub`, the Keycloak `sub` of who took it
    from the phone): all methods take `user_sub` and only operate on that user's
    captures — nobody can list or download another person's.
    """

    @abstractmethod
    def save(self, content: bytes, mime: str, user_sub: str) -> Capture:
        """Save a new photo for the user and return its metadata."""

    @abstractmethod
    def list_pending(self, user_sub: str) -> List[Capture]:
        """Unconsumed captures for the user, newest first."""

    @abstractmethod
    def get_image(self, id_captura: str, user_sub: str) -> Optional[Tuple[bytes, str]]:
        """Image bytes + mime for a capture, or None if missing / not owned by user."""

    @abstractmethod
    def discard(self, id_captura: str, user_sub: str) -> bool:
        """Remove a capture from the store (consumed by web, or discarded). True if it existed."""
