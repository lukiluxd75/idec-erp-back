"""
Use Case: Generación Transaccional de CITE (core del módulo).

Orquesta la generación atómica y concurrentemente segura de un CITE.
La lógica de bloqueo (SELECT FOR UPDATE) y el cálculo del correlativo
están encapsulados en el repositorio; este use_case solo aplica las
validaciones de dominio previas al intento transaccional.
"""
from app.domains.cite.domain.entities import DocumentoCite
from app.domains.cite.domain.exceptions import (
    ConfiguracionNotFoundException,
    GestionInactivaException,
)
from app.domains.cite.domain.ports import CiteRepositoryPort


class GenerarCiteUseCase:

    def __init__(self, repository: CiteRepositoryPort):
        self._repo = repository

    def execute(
        self,
        id_configuracion: int,
        referencia: str,
        id_funcionario_remitente: int,
    ) -> DocumentoCite:
        # ── Validar que la configuración exista ───────────────────────────────
        configuracion = self._repo.get_configuracion_by_id(id_configuracion)
        if configuracion is None:
            raise ConfiguracionNotFoundException(
                f"No existe una configuración CITE con id={id_configuracion}."
            )

        # ── Validar que la gestión esté activa ────────────────────────────────
        # gestion_activa viene denormalizado desde el JOIN en el repositorio.
        if not configuracion.gestion_activa:
            raise GestionInactivaException(
                f"La gestión asociada a la configuración '{configuracion.prefijo}' "
                "no está activa. No se pueden generar CITEs en gestiones cerradas."
            )

        # ── Validar que la configuración esté activa ──────────────────────────
        if not configuracion.activo:
            raise ConfiguracionNotFoundException(
                f"La configuración CITE '{configuracion.prefijo}' está inactiva. "
                "Contacte al administrador del sistema."
            )

        # ── Delegar la transacción atómica al repositorio ─────────────────────
        # Toda la concurrencia (lock, MAX+1, INSERT, REFRESH) ocurre aquí.
        return self._repo.generar_cite(
            id_configuracion=id_configuracion,
            referencia=referencia,
            id_funcionario_remitente=id_funcionario_remitente,
        )
