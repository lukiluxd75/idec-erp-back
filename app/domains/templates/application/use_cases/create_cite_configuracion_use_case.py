from app.domains.templates.domain.entities.cite import CiteConfiguracion, render_cite_formato
from app.domains.templates.domain.ports.cite_repository_port import CiteRepositoryPort


class CreateCiteConfiguracionUseCase:
    """Use case: register a new sigla (area + tipo_documento combination). Each
    sigla gets its own independent correlative counter -- switching between
    siglas is what makes the numbering 'restart at 01' for a combination that
    has never been used before (see CiteRepositoryPort.generate)."""

    def __init__(self, repository: CiteRepositoryPort):
        self._repository = repository

    def execute(
        self,
        area_codigo: str,
        tipo_documento_codigo: str,
        nombre: str,
        formato: str,
        longitud_numero: int,
        reinicia_por_gestion: bool,
    ) -> CiteConfiguracion:
        render_cite_formato(
            formato,
            area=area_codigo,
            tipo=tipo_documento_codigo,
            numero="0".zfill(longitud_numero),
            gestion=2000,
        )

        configuracion = CiteConfiguracion(
            id=None,
            area_codigo=area_codigo,
            tipo_documento_codigo=tipo_documento_codigo,
            nombre=nombre,
            formato=formato,
            longitud_numero=longitud_numero,
            reinicia_por_gestion=reinicia_por_gestion,
        )
        return self._repository.create_configuracion(configuracion)
