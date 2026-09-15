from app.domains.detection.infrastructure.gpu_detection_client import GpuDetectionClient


def get_detection_engine() -> GpuDetectionClient:
    return GpuDetectionClient()
