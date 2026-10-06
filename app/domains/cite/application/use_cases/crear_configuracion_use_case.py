"""
Use Case: Crear una nueva ConfiguracionCite para un área en una gestión.

Reglas de negocio verificadas:
  - La gestión debe existir.
  - La gestión debe estar activa (activa=True).
  - El área debe existir.
  - El prefijo no debe existir ya para esa gestión (UNIQUE(id_gestion, prefijo)).
"""
from app.domains.cite.domain.entities import ConfiguracionCite
from app.domains.cite.domain.exceptions import (
    AreaNotFoundException,
    GestionInactivaException,
    GestionNotFoundException,
    PrefijoDuplicadoException,
)
from app.domains.cite.domain.ports import CiteRepositoryPort


class CrearConfiguracionCiteUseCase:

    def __init__(self, repository: CiteRepositoryPort):
        self._repo = repository

    def execute(
        self,
        id_area: int,
        id_gestion: int,
        prefijo: str,
    ) -> ConfiguracionCite:
        # ── Validar existencia de gestión ─────────────────────────────────────
        gestion = self._repo.get_gestion_by_id(id_gestion)
        if gestion is None:
            raise GestionNotFoundException(
                f"No existe una gestión con id_gestion={id_gestion}."
            )

        # ── Validar que la gestión esté activa ────────────────────────────────
        if not gestion.activa:
            raise GestionInactivaException(
                f"La gestión {gestion.anio} (id={id_gestion}) no está activa. "
                "No se pueden crear configuraciones en gestiones cerradas."
            )

        # ── Validar existencia de área ────────────────────────────────────────
        area = self._repo.get_area_by_id(id_area)
        if area is None:
            raise AreaNotFoundException(
                f"No existe un área con id_area={id_area}."
            )

        # ── Validar unicidad del prefijo en la gestión ────────────────────────
        prefijo_upper = prefijo.strip().upper()
        if self._repo.prefijo_existe_en_gestion(id_gestion, prefijo_upper):
            raise PrefijoDuplicadoException(
                f"El prefijo '{prefijo_upper}' ya existe para la gestión {gestion.anio}. "
                "Cada prefijo debe ser único por año/gestión."
            )

        return self._repo.crear_configuracion(
            id_area=id_area,
            id_gestion=id_gestion,
            prefijo=prefijo_upper,
        )
