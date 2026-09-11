from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from app.domains.resoluciones.domain.entities.resolucion import Resolucion


class ResolucionRepositoryPort(ABC):
    """
    Puerto que la infraestructura de Resoluciones debe implementar (ver CLAUDE.md §3).
    application/ solo conoce esta interfaz, nunca SQLAlchemy ni el esquema real de la BD.

    Cada resolución pertenece a un usuario (`user_sub`, el `sub` de Keycloak de quien la
    subió desde la app móvil): todos los métodos que leen/escriben una resolución
    puntual reciben `user_sub` y solo operan sobre resoluciones de ese usuario — así
    "Mis resoluciones" en el frontend no puede ver ni tocar las de otra persona.
    """

    @abstractmethod
    def listar(self, user_sub: str) -> List[Resolucion]:
        """Las resoluciones (no borradas) del usuario, más nuevas primero."""

    @abstractmethod
    def obtener(self, id_resolucion: str, user_sub: str) -> Optional[Resolucion]:
        """Detalle de una resolución del usuario, o None si no existe / no es suya."""

    @abstractmethod
    def obtener_pagina(self, id_resolucion: str, orden: int, user_sub: str) -> Optional[Tuple[bytes, str]]:
        """Bytes de imagen + mime de una página, o None si no existe / no es del usuario."""

    @abstractmethod
    def crear(
        self,
        nombre: str,
        nro_resolucion: str,
        paginas: List[Tuple[bytes, str]],
        user_sub: str,
    ) -> Resolucion:
        """Crea una resolución nueva del usuario con sus páginas (bytes + mime, en orden)."""

    @abstractmethod
    def guardar_tabla(
        self, id_resolucion: str, tabla: Dict[str, Any], estado: str, user_sub: str
    ) -> Optional[Resolucion]:
        """Actualiza la tabla (JSON opaco) y el estado. None si no existe / no es del usuario."""

    @abstractmethod
    def eliminar(self, id_resolucion: str, user_sub: str) -> bool:
        """Borra (soft delete) una resolución del usuario. True si existía y era suya."""
