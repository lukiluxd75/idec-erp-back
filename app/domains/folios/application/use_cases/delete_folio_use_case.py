from app.domains.folios.domain.exceptions import FolioNotFoundException
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort


class DeleteFolioUseCase:
    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, folio_id: str, user_sub: str) -> None:
        if not self._repo.soft_delete(folio_id, user_sub):
            raise FolioNotFoundException("El folio no existe.")
