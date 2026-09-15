from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.core.config.settings import settings
from app.domains.detection.domain.exceptions import DetectionEngineError, DetectionEngineUnavailable
from app.domains.detection.infrastructure.gpu_detection_client import GpuDetectionClient
from app.domains.detection.presentation.deps import get_detection_engine
from app.domains.detection.presentation.schemas.detection_schema import AlignManualRequest, DetectChangesRequest
from app.domains.security.contracts import UserProfile, get_current_user, require_permission

router = APIRouter(tags=["Detección de construcciones"])


def _raise_engine(exc: Exception) -> None:
    if isinstance(exc, DetectionEngineUnavailable):
        raise HTTPException(status_code=503, detail=str(exc.detail)) from exc
    if isinstance(exc, DetectionEngineError):
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    raise


@router.get("/health")
def engine_health(
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Health of the remote GPU detection engine (does not expose the engine host to the browser)."""
    try:
        data = engine.health()
        return {
            "engine_url": settings.DETECTION_ENGINE_URL,
            "reachable": True,
            "engine": data,
        }
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        return {
            "engine_url": settings.DETECTION_ENGINE_URL,
            "reachable": False,
            "detail": getattr(exc, "detail", str(exc)),
        }


@router.get("/wms/layers")
def list_wms_layers(
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    try:
        return engine.list_wms_layers()
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.post("/jobs/detect-wms")
def start_detect_wms(
    payload: DetectChangesRequest,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.edit")),
):
    """Start an async WMS change-detection job on the GPU engine."""
    try:
        return engine.start_detect_wms_async(payload.model_dump(exclude_none=True))
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.get("/jobs/{job_id}/progress")
def job_progress(
    job_id: str,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    try:
        return engine.get_progress(job_id)
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.get("/jobs/{job_id}/result")
def job_result(
    job_id: str,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    try:
        return engine.get_result(job_id)
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.edit")),
):
    try:
        return engine.cancel_job(job_id)
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.get("/jobs/{job_id}/manual-align")
def get_align_manual(
    job_id: str,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    try:
        return engine.get_align_manual(job_id)
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.post("/jobs/{job_id}/manual-align/preview")
def preview_align_manual(
    job_id: str,
    payload: AlignManualRequest,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.edit")),
):
    try:
        return engine.preview_align_manual(job_id, payload.model_dump())
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.post("/jobs/{job_id}/manual-align/apply")
def apply_align_manual(
    job_id: str,
    payload: AlignManualRequest,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.edit")),
):
    try:
        return engine.apply_align_manual(job_id, payload.model_dump())
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.get("/cadastre/cadastral-record/{id_registro}")
def registro_catastral(
    id_registro: int,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """SISCAT cadastral registry detail (read-only via GPU engine)."""
    try:
        return engine.get_registro_catastral(id_registro)
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)


@router.get("/engine/{asset_path:path}")
def proxy_engine_asset(
    asset_path: str,
    engine: GpuDetectionClient = Depends(get_detection_engine),
    _user: UserProfile = Depends(get_current_user),
):
    """Authenticated reverse-proxy for engine images/files (browser never talks to :8100)."""
    try:
        binary = engine.fetch_path(asset_path)
    except (DetectionEngineUnavailable, DetectionEngineError) as exc:
        _raise_engine(exc)
        return None
    headers = {}
    if binary.filename:
        headers["Content-Disposition"] = f'inline; filename="{binary.filename}"'
    return Response(content=binary.content, media_type=binary.content_type, headers=headers)
