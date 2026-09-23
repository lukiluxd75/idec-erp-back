from typing import Any, Dict

from app.domains.folios.domain.entities.folio import Folio, FolioStatus
from app.domains.folios.domain.exceptions import (
    FolioNotEditableException,
    FolioNotFoundException,
    InvalidFolioUploadException,
)
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort


class ReviewFolioUseCase:
    """Save the reviewer's corrected JSON (and optionally confirm it). The
    extracted version is kept untouched next to it."""

    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, folio_id: str, user_sub: str, data: Dict[str, Any], confirm: bool) -> Folio:
        folio = self._repo.get(folio_id, user_sub)
        if folio is None:
            raise FolioNotFoundException("El folio no existe.")
        if folio.status in (FolioStatus.PENDING, FolioStatus.PROCESSING):
            raise FolioNotEditableException("El folio todavía se está procesando.")
        if not isinstance(data, dict) or not data:
            raise InvalidFolioUploadException("Los datos del folio están vacíos.")
        return self._repo.save_review(folio_id, user_sub, data, confirm)
