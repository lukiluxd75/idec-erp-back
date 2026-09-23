from typing import Any, Dict, List

from app.domains.folios.domain.exceptions import FolioNotFoundException
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort


class GetFolioDiagnosticsUseCase:
    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, folio_id: str, user_sub: str) -> List[Dict[str, Any]]:
        diagnostics = self._repo.get_diagnostics(folio_id, user_sub)
        if diagnostics is None:
            raise FolioNotFoundException("El folio no existe.")
        return diagnostics
