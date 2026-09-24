from typing import Any, Dict

from app.domains.folios.domain.exceptions import FolioNotFoundException
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort


class GetFolioFillLogUseCase:
    """How the last extraction filled each field (OCR text behind every header
    value, classification of every column A line, LLM proposals). {} when the
    folio has no log yet."""

    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, folio_id: str, user_sub: str) -> Dict[str, Any]:
        log = self._repo.get_fill_log(folio_id, user_sub)
        if log is None:
            raise FolioNotFoundException("El folio no existe.")
        return log
