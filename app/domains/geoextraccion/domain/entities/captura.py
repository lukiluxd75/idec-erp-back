"""Entidad de una captura enviada desde la app móvil (geoextract móvil: solo saca la
foto y la manda). Sin FastAPI, sin infraestructura de almacenamiento."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Captura:
    """Metadatos de una foto pendiente de cargar en CapturaPage. Los bytes de la
    imagen NO viajan en esta entidad — se piden aparte, como PaginaResolucion en el
    dominio resoluciones."""

    id_captura: str
    mime: str
    fecha_creacion: datetime
