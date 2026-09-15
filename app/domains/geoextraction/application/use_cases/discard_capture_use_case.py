from app.domains.geoextraction.domain.exceptions import CaptureNotFoundException
from app.domains.geoextraction.domain.ports.capture_store_port import CaptureStorePort


class DiscardCaptureUseCase:
    """Use case: remove a capture from the store — because the web already loaded
    it in the viewer, or because the user discarded it without using it."""

    def __init__(self, store: CaptureStorePort):
        self._store = store

    def execute(self, id_captura: str, user_sub: str) -> None:
        existed = self._store.discard(id_captura, user_sub)
        if not existed:
            raise CaptureNotFoundException(f"No hay ninguna captura pendiente con id '{id_captura}'.")
