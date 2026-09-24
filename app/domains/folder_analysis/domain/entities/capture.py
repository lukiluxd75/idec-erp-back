from dataclasses import dataclass
from datetime import datetime


class CaptureStatus:
    INBOX = "inbox"        # arrived from the phone, not sorted yet
    ASSIGNED = "assigned"  # page of a document


@dataclass
class Capture:
    """A photo sent from the mobile app. Image bytes are fetched separately."""

    id: str
    user_sub: str
    file_name: str
    mime: str
    status: str
    created_at: datetime
