from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.domains.geoextraccion.domain.entities.captura import Captura


class CapturaStorePort(ABC):
    """
    Puerto que la infraestructura de Geoextracción debe implementar (ver CLAUDE.md §3).
    application/ solo conoce esta interfaz, nunca cómo/dónde se guarda la foto de
    verdad (hoy: memoria del proceso — ver MemoriaCapturaStore; si algún día hace
    falta persistirla, se escribe otro adaptador acá sin tocar casos de uso).

    Cada captura pertenece a un usuario (`user_sub`, el `sub` de Keycloak de quien la
    sacó desde el celular): todos los métodos reciben `user_sub` y solo operan sobre
    capturas de ese usuario — nadie puede listar ni descargar las de otra persona.
    """

    @abstractmethod
    def guardar(self, contenido: bytes, mime: str, user_sub: str) -> Captura:
        """Guarda una foto nueva del usuario y devuelve sus metadatos."""

    @abstractmethod
    def listar_pendientes(self, user_sub: str) -> List[Captura]:
        """Las capturas no consumidas del usuario, más nuevas primero."""

    @abstractmethod
    def obtener_imagen(self, id_captura: str, user_sub: str) -> Optional[Tuple[bytes, str]]:
        """Bytes de imagen + mime de una captura, o None si no existe / no es del usuario."""

    @abstractmethod
    def descartar(self, id_captura: str, user_sub: str) -> bool:
        """Saca una captura del store (consumida por la web, o descartada). True si existía."""
