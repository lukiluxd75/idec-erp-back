from typing import Tuple

from app.domains.geoextraction.domain.exceptions import CaptureNotFoundException
from app.domains.geoextraction.domain.ports.capture_store_port import CaptureStorePort


class GetCaptureImageUseCase:
    """Use case: get image bytes for a pending capture so the web can load it
    in the CapturePage viewer."""

    def __init__(self, store: CaptureStorePort):
        self._store = store

    def execute(self, id_captura: str, user_sub: str) -> Tuple[bytes, str]:
        image = self._store.get_image(id_captura, user_sub)
        if image is None:
            raise CaptureNotFoundException(f"No hay ninguna captura pendiente con id '{id_captura}'.")
        return image
