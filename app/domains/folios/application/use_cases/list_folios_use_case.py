from typing import List

from app.domains.folios.domain.entities.folio import Folio
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort


class ListFoliosUseCase:
    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, user_sub: str) -> List[Folio]:
        return self._repo.list(user_sub)
