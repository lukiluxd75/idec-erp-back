from datetime import datetime

from pydantic import BaseModel


class CaptureListItem(BaseModel):
    """One row of 'Captures from the phone' in CapturePage."""

    capture_id: str
    mime: str
    created_at: datetime
