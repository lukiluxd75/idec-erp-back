from app.domains.deteccion.infrastructure.gpu_detection_client import GpuDetectionClient


def get_detection_engine() -> GpuDetectionClient:
    return GpuDetectionClient()
