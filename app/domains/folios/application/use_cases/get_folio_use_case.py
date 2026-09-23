from app.domains.folios.domain.entities.folio import Folio
from app.domains.folios.domain.exceptions import FolioNotFoundException
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort


class GetFolioUseCase:
    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, folio_id: str, user_sub: str) -> Folio:
        folio = self._repo.get(folio_id, user_sub)
        if folio is None:
            raise FolioNotFoundException("El folio no existe.")
        return folio
