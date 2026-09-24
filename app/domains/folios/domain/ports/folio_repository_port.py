from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from app.domains.folios.domain.entities.folio import Folio


class FolioRepositoryPort(ABC):
    """Persistence of folios and their page images. Every read/write that comes
    from a user request is scoped by `user_sub` (a folio belongs to whoever
    scanned it, same rule as resolutions/geoextraction). The `*_for_processing`
    methods are the exception: the background pipeline acts on a folio id it was
    handed by the upload request itself, no user in context."""

    @abstractmethod
    def create(self, user_sub: str, pages: List[Tuple[bytes, str]]) -> Folio:
        """New folio in PENDING with its pages (bytes, mime) in the given order."""

    @abstractmethod
    def list(self, user_sub: str) -> List[Folio]:
        """User's non-deleted folios, newest first (pages metadata included)."""

    @abstractmethod
    def get(self, folio_id: str, user_sub: str) -> Optional[Folio]:
        """None if missing, deleted, or not the user's."""

    @abstractmethod
    def get_page_image(
        self, folio_id: str, page_index: int, user_sub: str, upright: bool
    ) -> Optional[Tuple[bytes, str]]:
        """(bytes, mime). `upright=True` returns the rotated/deskewed copy the
        pipeline stored, falling back to the original if there is none yet."""

    @abstractmethod
    def get_diagnostics(self, folio_id: str, user_sub: str) -> Optional[List[Dict[str, Any]]]:
        """Raw per-page OCR/layout diagnostics saved by the pipeline."""

    @abstractmethod
    def get_fill_log(self, folio_id: str, user_sub: str) -> Optional[Dict[str, Any]]:
        """Fill log of the last extraction; None if the folio is missing, {} if
        it has none (not processed yet, or processed before logs existed)."""

    @abstractmethod
    def save_review(
        self, folio_id: str, user_sub: str, data: Dict[str, Any], confirm: bool
    ) -> Folio:
        """Store the reviewer's version of the data (and CONFIRMED if `confirm`)."""

    @abstractmethod
    def soft_delete(self, folio_id: str, user_sub: str) -> bool:
        """Mark deleted. True if it existed."""

    # ---- background pipeline ----

    @abstractmethod
    def get_for_processing(self, folio_id: str) -> Optional[Folio]:
        """Folio regardless of owner (None if missing/deleted)."""

    @abstractmethod
    def get_page_bytes_for_processing(self, folio_id: str) -> List[Tuple[int, bytes, str]]:
        """(page_index, original bytes, mime) for every page, in order."""

    @abstractmethod
    def mark_processing(self, folio_id: str) -> None:
        """Status PROCESSING; clears the previous error, fill log and any unconfirmed review."""

    @abstractmethod
    def save_page_result(
        self,
        folio_id: str,
        page_index: int,
        upright_jpeg: Optional[bytes],
        rotation_deg: Optional[float],
        detected_page_number: Optional[int],
        diagnostics: Dict[str, Any],
    ) -> None:
        """Per-page output of the pipeline."""

    @abstractmethod
    def save_extraction(
        self,
        folio_id: str,
        data: Dict[str, Any],
        status: str,
        matricula: Optional[str],
        fill_log: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Final extracted JSON + READY/NEEDS_REVIEW (stamps processed_at), and
        the log of how it was filled."""

    @abstractmethod
    def mark_failed(self, folio_id: str, message: str) -> None:
        """Status FAILED with a user-facing message."""
