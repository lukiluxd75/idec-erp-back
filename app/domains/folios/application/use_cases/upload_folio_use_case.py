from typing import List, Tuple

from app.domains.folios.domain.entities.folio import Folio
from app.domains.folios.domain.exceptions import InvalidFolioUploadException
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}
MAX_PAGES = 10
MAX_PAGE_BYTES = 15 * 1024 * 1024


class UploadFolioUseCase:
    """Register a folio scanned from the phone (1..N page photos, scan order).
    Processing is NOT done here -- the endpoint schedules ProcessFolioUseCase."""

    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, pages: List[Tuple[bytes, str]], user_sub: str) -> Folio:
        if not pages:
            raise InvalidFolioUploadException("Debe enviar al menos una página del folio.")
        if len(pages) > MAX_PAGES:
            raise InvalidFolioUploadException(f"Un folio admite como máximo {MAX_PAGES} páginas.")
        for i, (content, mime) in enumerate(pages, start=1):
            if not content:
                raise InvalidFolioUploadException(f"La página {i} llegó vacía.")
            if mime not in ALLOWED_MIMES:
                raise InvalidFolioUploadException(
                    f"La página {i} tiene un formato no soportado ({mime}). Se espera JPEG, PNG o WEBP."
                )
            if len(content) > MAX_PAGE_BYTES:
                raise InvalidFolioUploadException(f"La página {i} supera los 15 MB.")
        return self._repo.create(user_sub=user_sub, pages=pages)
