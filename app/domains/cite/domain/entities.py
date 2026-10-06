"""
Entidades de dominio puro (dataclasses, sin acoplamiento ORM).
Representan el estado del negocio que los use_cases manipulan.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Gestion:
    id_gestion: int
    anio: int
    fecha_inicial: date
    fecha_final: date
    activa: bool


@dataclass
class Area:
    id_area: int
    nombre: str
    tipo: str  # 'Secretaria' | 'Direccion' | 'Jefatura' | 'Unidad'
    id_area_padre: Optional[int] = None


@dataclass
class ConfiguracionCite:
    id_configuracion: int
    id_area: int
    id_gestion: int
    prefijo: str
    activo: bool
    # Campos denormalizados útiles para el generador (evitan un JOIN extra)
    gestion_activa: bool = field(default=True)


@dataclass
class DocumentoCite:
    id_documento: int
    id_configuracion: int
    prefijo: str
    correlativo: int
    codigo_cite_completo: str          # ej. "DGC-001"
    fecha_generacion: datetime
    referencia: str
    id_funcionario_remitente: int
