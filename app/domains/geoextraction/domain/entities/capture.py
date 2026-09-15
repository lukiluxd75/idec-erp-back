"""Entity for a capture sent from the mobile app (mobile geoextract: only takes
the photo and sends it). No FastAPI, no storage infrastructure."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Capture:
    """Metadata for a photo pending load in CapturePage. Image bytes do NOT travel
    in this entity — they are fetched separately, like ResolutionPage in the
    resolutions domain."""

    id_captura: str
    mime: str
    fecha_creacion: datetime
