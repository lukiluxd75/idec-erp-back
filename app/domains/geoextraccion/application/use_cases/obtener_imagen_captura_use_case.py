from typing import Tuple

from app.domains.geoextraccion.domain.exceptions import CapturaNoEncontradaException
from app.domains.geoextraccion.domain.ports.captura_store_port import CapturaStorePort


class ObtenerImagenCapturaUseCase:
    """Caso de uso: obtener los bytes de imagen de una captura pendiente, para que la
    web la cargue en el visor de CapturaPage."""

    def __init__(self, store: CapturaStorePort):
        self._store = store

    def execute(self, id_captura: str, user_sub: str) -> Tuple[bytes, str]:
        imagen = self._store.obtener_imagen(id_captura, user_sub)
        if imagen is None:
            raise CapturaNoEncontradaException(f"No hay ninguna captura pendiente con id '{id_captura}'.")
        return imagen
