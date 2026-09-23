from typing import Tuple

from app.domains.folios.domain.exceptions import FolioNotFoundException
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort


class GetFolioPageImageUseCase:
    def __init__(self, repository: FolioRepositoryPort):
        self._repo = repository

    def execute(self, folio_id: str, page_index: int, user_sub: str, upright: bool) -> Tuple[bytes, str]:
        image = self._repo.get_page_image(folio_id, page_index, user_sub, upright)
        if image is None:
            raise FolioNotFoundException("La página no existe.")
        return image
