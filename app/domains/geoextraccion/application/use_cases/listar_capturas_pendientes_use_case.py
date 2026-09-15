from typing import List

from app.domains.geoextraccion.domain.entities.captura import Captura
from app.domains.geoextraccion.domain.ports.captura_store_port import CapturaStorePort


class ListarCapturasPendientesUseCase:
    """Caso de uso: listar las capturas que el usuario mandó desde el celular y
    todavía no cargó en CapturaPage."""

    def __init__(self, store: CapturaStorePort):
        self._store = store

    def execute(self, user_sub: str) -> List[Captura]:
        return self._store.listar_pendientes(user_sub)
