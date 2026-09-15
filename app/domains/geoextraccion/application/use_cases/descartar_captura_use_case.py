from app.domains.geoextraccion.domain.exceptions import CapturaNoEncontradaException
from app.domains.geoextraccion.domain.ports.captura_store_port import CapturaStorePort


class DescartarCapturaUseCase:
    """Caso de uso: sacar una captura del store — porque la web ya la cargó en el
    visor, o porque el usuario decidió descartarla sin usarla."""

    def __init__(self, store: CapturaStorePort):
        self._store = store

    def execute(self, id_captura: str, user_sub: str) -> None:
        existia = self._store.descartar(id_captura, user_sub)
        if not existia:
            raise CapturaNoEncontradaException(f"No hay ninguna captura pendiente con id '{id_captura}'.")
