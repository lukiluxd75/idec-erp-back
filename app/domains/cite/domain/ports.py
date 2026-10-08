"""
Puerto (interfaz) del repositorio CITE.
Los use_cases dependen únicamente de este contrato —
la implementación concreta (SQL) vive en infrastructure/.
"""
from abc import ABC, abstractmethod
from typing import Optional

from app.domains.cite.domain.entities import (
    Area,
    ConfiguracionCite,
    DocumentoCite,
    Gestion,
)


class CiteRepositoryPort(ABC):

    # ── Gestión ──────────────────────────────────────────────────────────────

    @abstractmethod
    def get_gestion_activa(self) -> Optional[Gestion]:
        """Devuelve la única gestión con activa=True, o None si no existe."""

    @abstractmethod
    def get_gestion_by_id(self, id_gestion: int) -> Optional[Gestion]:
        """Busca una gestión por PK."""

    # ── Área ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def get_area_by_id(self, id_area: int) -> Optional[Area]:
        """Busca un área por PK."""

    # ── ConfiguracionCite ────────────────────────────────────────────────────

    @abstractmethod
    def get_configuracion_by_id(self, id_configuracion: int) -> Optional[ConfiguracionCite]:
        """Busca una configuración por PK (con join a gestión para leer activa)."""

    @abstractmethod
    def prefijo_existe_en_gestion(self, id_gestion: int, prefijo: str) -> bool:
        """True si ya existe ese prefijo para la gestión dada (constraint UNIQUE)."""

    @abstractmethod
    def crear_configuracion(
        self,
        id_area: int,
        id_gestion: int,
        prefijo: str,
    ) -> ConfiguracionCite:
        """Persiste una nueva configuracion_cite y la devuelve."""

    # ── DocumentoCite (core transaccional) ───────────────────────────────────

    @abstractmethod
    def generar_cite(
        self,
        id_configuracion: int,
        referencia: str,
        id_funcionario_remitente: int,
    ) -> DocumentoCite:
        """
        Operación atómica con bloqueo de fila:
          1. SELECT ... FOR UPDATE del último correlativo de id_configuracion.
          2. Calcula siguiente correlativo (MAX + 1 ó 1 si no hay registros).
          3. Inserta documento_cite con prefijo físico (la columna generada no se escribe).
          4. Devuelve la entidad con el código CITE completo.
        Lanza CiteGenerationException si hay un fallo irrecuperable.
        """
