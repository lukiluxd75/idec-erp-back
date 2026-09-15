from datetime import datetime

from pydantic import BaseModel


class CaptureListItem(BaseModel):
    """One row of 'Captures from the phone' in CapturePage."""

    id_captura: str
    mime: str
    fecha_creacion: datetime
