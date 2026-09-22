from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.domains.templates.domain.exceptions import InvalidCiteFormatException

ESTADOS_CITE = ("GENERADO", "ANULADO")


def render_cite_formato(formato: str, *, area: str, tipo: str, numero: str, gestion: int) -> str:
    """Substitutes the sigla's `formato` template, e.g. 'GAMC-{area}-{tipo}-{numero}/{gestion}'.
    Shared by CreateCiteConfiguracionUseCase (validates on save) and
    SqlCiteRepository.generate() (renders the real code) so a bad formato is
    rejected before it is ever persisted."""
    try:
        return formato.format(area=area, tipo=tipo, numero=numero, gestion=gestion)
    except (KeyError, IndexError, ValueError) as exc:
        raise InvalidCiteFormatException(
            "El formato solo puede usar los placeholders {area}, {tipo}, {numero} y {gestion} "
            "(use '{{' y '}}' para una llave literal)."
        ) from exc


@dataclass
class CiteConfiguracion:
    """Una 'sigla' de CITE: combinación única de área + tipo de documento, con su
    propio formato y contador independiente (ver plantillas_dinamicas.cite_configuracion).
    Cambiar de sigla (otra área u otro tipo de documento) usa otra fila de esta
    tabla y, por lo tanto, otro contador -- empieza en 0/01 la primera vez que se
    genera un CITE con esa combinación."""

    id: Optional[int]
    area_codigo: str
    tipo_documento_codigo: str
    nombre: str
    formato: str
    longitud_numero: int = 5
    reinicia_por_gestion: bool = True
    activa: bool = True


@dataclass
class CiteGenerado:
    """Un CITE ya emitido y asociado (opcionalmente) a un documento/trámite
    concretos (ver plantillas_dinamicas.cite_generado)."""

    id: Optional[int]
    cite_configuracion_id: int
    gestion: int
    numero_correlativo: int
    codigo: str
    documento_id: Optional[int] = None
    tramite_id: Optional[int] = None
    estado: str = "GENERADO"
    motivo_anulacion: Optional[str] = None
    generado_en: Optional[datetime] = None
    generado_por: Optional[str] = None
