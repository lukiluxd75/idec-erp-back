class DetectionDomainException(Exception):
    """Base exception for the construction-detection domain."""


class DetectionEngineUnavailable(DetectionDomainException):
    def __init__(self, detail: str = "Detection engine is unavailable."):
        super().__init__(detail)
        self.detail = detail


class DetectionEngineError(DetectionDomainException):
    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
