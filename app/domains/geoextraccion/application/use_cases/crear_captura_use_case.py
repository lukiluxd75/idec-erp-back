from app.domains.geoextraccion.domain.entities.captura import Captura
from app.domains.geoextraccion.domain.exceptions import CapturaInvalidaException
from app.domains.geoextraccion.domain.ports.captura_store_port import CapturaStorePort

MIMES_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}


class CrearCapturaUseCase:
    """Caso de uso: registrar una foto recién sacada desde la app móvil, para que
    quede pendiente de cargarse en CapturaPage (geoextract móvil: solo saca la foto y
    la manda — el resto del flujo sigue siendo de la web)."""

    def __init__(self, store: CapturaStorePort):
        self._store = store

    def execute(self, contenido: bytes, mime: str, user_sub: str) -> Captura:
        if not contenido:
            raise CapturaInvalidaException("La captura llegó vacía.")
        if mime not in MIMES_PERMITIDOS:
            raise CapturaInvalidaException(
                f"Formato de imagen no soportado ({mime}). Se espera JPEG, PNG o WEBP."
            )
        return self._store.guardar(contenido=contenido, mime=mime, user_sub=user_sub)
