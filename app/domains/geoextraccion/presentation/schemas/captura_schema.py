from datetime import datetime

from pydantic import BaseModel


class CapturaListItem(BaseModel):
    """Una fila de 'Capturas desde el celular' en CapturaPage."""

    id_captura: str
    mime: str
    fecha_creacion: datetime
