from abc import ABC, abstractmethod
from typing import List, Optional

from app.domains.templates.domain.entities.cite import CiteConfiguracion, CiteGenerado


class CiteRepositoryPort(ABC):
    """
    Port that Templates infrastructure must implement for CITES (see CLAUDE.md §3).
    application/ only knows this interface, never SQLAlchemy or the real DB schema.
    """

    @abstractmethod
    def list_configuraciones(self) -> List[CiteConfiguracion]:
        """Every registered sigla (active and inactive), by name."""

    @abstractmethod
    def get_configuracion(
        self, area_codigo: str, tipo_documento_codigo: str
    ) -> Optional[CiteConfiguracion]:
        """Lookup by the unique (area_codigo, tipo_documento_codigo) combination."""

    @abstractmethod
    def create_configuracion(self, configuracion: CiteConfiguracion) -> CiteConfiguracion:
        """Register a new sigla."""

    @abstractmethod
    def generate(
        self,
        configuracion: CiteConfiguracion,
        gestion: int,
        documento_id: Optional[int],
        tramite_id: Optional[int],
        user_sub: str,
    ) -> CiteGenerado:
        """
        Atomically takes the next correlative number for `configuracion` (locking
        the counter row so concurrent requests never hand out the same number --
        see database/plantillas_dinamicas_postgresql.sql's own comment on
        cite_correlativo), formats the code and inserts the cite_generado row.

        If `configuracion.reinicia_por_gestion` is True, the counter is scoped to
        (configuracion, gestion): a `gestion` never used before for this
        configuracion starts at 0 -- i.e. the first CITE generated is number 1
        ("01"). This is also what happens automatically the first time a
        DIFFERENT sigla (a different configuracion) is used: it has never had a
        counter row before, so it starts at 0/01 too.

        If `reinicia_por_gestion` is False, the running total carries forward
        across gestiones instead of resetting every year.
        """

    @abstractmethod
    def list_generados(self) -> List[CiteGenerado]:
        """Every emitted CITE, newest first."""
