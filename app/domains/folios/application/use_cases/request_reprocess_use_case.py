from app.domains.folios.domain.entities.folio import Folio, FolioStatus
from app.domains.folios.domain.exceptions import FolioNotEditableException, FolioNotFoundException
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort


class RequestReprocessUseCase:
    """Validate a reprocess request; the endpoint then schedules the pipeline
    again. A confirmed folio is final (its reviewed data would stop matching a
    fresh extraction)."""

    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, folio_id: str, user_sub: str) -> Folio:
        folio = self._repo.get(folio_id, user_sub)
        if folio is None:
            raise FolioNotFoundException("El folio no existe.")
        if folio.status == FolioStatus.CONFIRMED:
            raise FolioNotEditableException("El folio ya fue confirmado; no se puede reprocesar.")
        self._repo.mark_processing(folio_id)
        return self._repo.get(folio_id, user_sub)
