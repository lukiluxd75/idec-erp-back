from dataclasses import dataclass
from datetime import datetime


class CaptureStatus:
    INBOX = "inbox"        # arrived from the phone, not sorted yet
    ASSIGNED = "assigned"  # page of a document


class CaptureVariant:
    """Which copy of the photo is being asked for. A phone photo weighs several
    megabytes; only the viewer, and only once the architect zooms in past what
    the preview can show, is worth that download."""

    THUMBNAIL = "thumbnail"  # list rows and page strips
    PREVIEW = "preview"      # what the viewer opens with
    ORIGINAL = "original"    # the upload as it arrived, for real zoom

    ALL = (THUMBNAIL, PREVIEW, ORIGINAL)


@dataclass
class Capture:
    """A photo sent from the mobile app. Image bytes are fetched separately."""

    id: str
    user_sub: str
    file_name: str
    mime: str
    status: str
    created_at: datetime
