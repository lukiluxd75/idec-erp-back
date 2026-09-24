from datetime import datetime
from typing import Optional

from app.domains.templates.domain.entities.cite import CiteGenerado
from app.domains.templates.domain.exceptions import CiteConfigurationNotFoundException
from app.domains.templates.domain.ports.cite_repository_port import CiteRepositoryPort


class GenerateCiteUseCase:
    """Use case: emit the next CITE for a sigla (area + tipo_documento). The
    counter is scoped to that exact sigla (see CiteRepositoryPort.generate), so
    using a DIFFERENT sigla than the last one always starts from its own
    untouched counter -- 01 the first time that combination is ever used."""

    def __init__(self, repository: CiteRepositoryPort):
        self._repository = repository

    def execute(
        self,
        area_codigo: str,
        tipo_documento_codigo: str,
        documento_id: Optional[int],
        tramite_id: Optional[int],
        user_sub: str,
        gestion: Optional[int] = None,
    ) -> CiteGenerado:
        configuracion = self._repository.get_configuracion(area_codigo, tipo_documento_codigo)
        if configuracion is None or not configuracion.activa:
            raise CiteConfigurationNotFoundException(
                f"No hay una sigla activa registrada para área '{area_codigo}' y tipo de "
                f"documento '{tipo_documento_codigo}'. Créela primero en Configuración de CITES."
            )

        return self._repository.generate(
            configuracion=configuracion,
            gestion=gestion or datetime.utcnow().year,
            documento_id=documento_id,
            tramite_id=tramite_id,
            user_sub=user_sub,
        )
