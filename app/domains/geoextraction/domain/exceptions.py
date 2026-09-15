from app.core.errors.exceptions import DomainException


class InvalidGeometryException(DomainException):
    """No received parcel has enough points to form a valid polygon."""
    http_status = 400


class UnreadableShapefileException(DomainException):
    """An uploaded file could not be read as a valid Shapefile, or none was uploaded."""
    http_status = 400


class CaptureNotFoundException(DomainException):
    """No pending capture with that id for the user (missing, not owned, or already
    expired/consumed — the store does not distinguish the three cases; see
    SqlCaptureStore)."""
    http_status = 404


class InvalidCaptureException(DomainException):
    """The photo uploaded from the phone arrived empty or in an unsupported format."""
    http_status = 400


__all__ = [
    "InvalidGeometryException",
    "UnreadableShapefileException",
    "CaptureNotFoundException",
    "InvalidCaptureException",
]
