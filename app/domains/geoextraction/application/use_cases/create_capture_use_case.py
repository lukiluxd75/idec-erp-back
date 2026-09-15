from app.domains.geoextraction.domain.entities.capture import Capture
from app.domains.geoextraction.domain.exceptions import InvalidCaptureException
from app.domains.geoextraction.domain.ports.capture_store_port import CaptureStorePort

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}


class CreateCaptureUseCase:
    """Use case: register a photo just taken from the mobile app, so it stays
    pending load in CapturePage (mobile geoextract: only takes the photo and
    sends it — the rest of the flow stays on the web)."""

    def __init__(self, store: CaptureStorePort):
        self._store = store

    def execute(self, content: bytes, mime: str, user_sub: str) -> Capture:
        if not content:
            raise InvalidCaptureException("La captura llegó vacía.")
        if mime not in ALLOWED_MIMES:
            raise InvalidCaptureException(
                f"Formato de imagen no soportado ({mime}). Se espera JPEG, PNG o WEBP."
            )
        return self._store.save(content=content, mime=mime, user_sub=user_sub)
