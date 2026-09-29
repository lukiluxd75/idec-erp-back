from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.domains.alignment.application.use_cases import (
    ConfirmAlignmentBlockUseCase,
    CreateAlignmentBlockUseCase,
    DeleteAlignmentBlockUseCase,
    GetAlignmentBlockUseCase,
    GetAlignmentCoverageUseCase,
    ListAlignmentBlocksUseCase,
    UpdateAlignmentBlockUseCase,
)
from app.domains.alignment.domain.entities.alignment_block import ControlPointRecord
from app.domains.alignment.domain.exceptions import AlignmentBlockNotFound, InvalidControlPoints
from app.domains.alignment.infrastructure.gis_layers_client import (
    GisLayersUnavailable,
    fetch_wms_image,
    list_wms_layers,
)
from app.domains.alignment.presentation.deps import (
    get_confirm_alignment_block_use_case,
    get_create_alignment_block_use_case,
    get_delete_alignment_block_use_case,
    get_get_alignment_block_use_case,
    get_get_alignment_coverage_use_case,
    get_list_alignment_blocks_use_case,
    get_update_alignment_block_use_case,
)
from app.domains.alignment.presentation.schemas.alignment_schema import (
    AlignmentBlockDetailSchema,
    AlignmentBlockSummary,
    AlignmentCoverageSummary,
    ControlPointInput,
    CreateAlignmentBlockRequest,
    UpdateAlignmentBlockRequest,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Alineación — georreferenciación manual por manzana"])


def _to_control_points(points: List[ControlPointInput]) -> List[ControlPointRecord]:
    return [
        ControlPointRecord(
            order_index=idx,
            lon_ref=p.lon_ref,
            lat_ref=p.lat_ref,
            lon_mov=p.lon_mov,
            lat_mov=p.lat_mov,
        )
        for idx, p in enumerate(points)
    ]


@router.get("/wms/layers")
def get_wms_layers(
    _user: UserProfile = Depends(require_permission("alignment.view")),
):
    """The same orthophoto WMS catalog (years, ArcGIS service names, GIS
    hosts) the map's basemap picker needs -- see gis_layers_client.py."""
    try:
        return list_wms_layers()
    except GisLayersUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc


@router.get("/wms/image")
def get_wms_image(
    host: str = Query(...),
    service: str = Query(...),
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    width: int = Query(1024),
    height: int = Query(1024),
    _user: UserProfile = Depends(require_permission("alignment.view")),
):
    """Proxies a raw WMS GetMap PNG for the given bbox -- the "before"
    (un-corrected) imagery the frontend warps client-side onto a block's
    fitted transform to show the correction result (see AlignmentPage)."""
    try:
        content = fetch_wms_image(host, service, (min_lon, min_lat, max_lon, max_lat), width, height)
    except GisLayersUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc
    return Response(content=content, media_type="image/png")


@router.post("/blocks", response_model=AlignmentBlockSummary)
def create_alignment_block(
    payload: CreateAlignmentBlockRequest,
    use_case: CreateAlignmentBlockUseCase = Depends(get_create_alignment_block_use_case),
    _user: UserProfile = Depends(require_permission("alignment.edit")),
):
    """Saves a new manzana-sized correction (draft) for a year, fitting an
    affine transform from the given control points."""
    try:
        return use_case.execute(
            year=payload.year,
            ring=payload.ring,
            control_points=_to_control_points(payload.control_points),
            created_by_sub=_user.sub,
        )
    except InvalidControlPoints as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


@router.get("/blocks", response_model=List[AlignmentBlockSummary])
def list_alignment_blocks(
    year: int = Query(...),
    use_case: ListAlignmentBlocksUseCase = Depends(get_list_alignment_blocks_use_case),
    _user: UserProfile = Depends(require_permission("alignment.view")),
):
    """Every block already drawn for a year, for the map overlay (each block
    renders as its own georeferenced layer -- see the module's design)."""
    return use_case.execute(year=year)


@router.get("/blocks/{block_id}", response_model=AlignmentBlockDetailSchema)
def get_alignment_block(
    block_id: int,
    use_case: GetAlignmentBlockUseCase = Depends(get_get_alignment_block_use_case),
    _user: UserProfile = Depends(require_permission("alignment.view")),
):
    detail = use_case.execute(block_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Manzana alineada no encontrada.")
    return detail


@router.put("/blocks/{block_id}", response_model=AlignmentBlockSummary)
def update_alignment_block(
    block_id: int,
    payload: UpdateAlignmentBlockRequest,
    use_case: UpdateAlignmentBlockUseCase = Depends(get_update_alignment_block_use_case),
    _user: UserProfile = Depends(require_permission("alignment.edit")),
):
    """Re-draws a block's polygon/control points and recomputes its
    transform -- drops it back to 'draft', it needs re-confirming."""
    try:
        return use_case.execute(
            block_id=block_id,
            ring=payload.ring,
            control_points=_to_control_points(payload.control_points),
        )
    except AlignmentBlockNotFound as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except InvalidControlPoints as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


@router.post("/blocks/{block_id}/confirm", response_model=AlignmentBlockSummary)
def confirm_alignment_block(
    block_id: int,
    use_case: ConfirmAlignmentBlockUseCase = Depends(get_confirm_alignment_block_use_case),
    _user: UserProfile = Depends(require_permission("alignment.edit")),
):
    """Marks a block as trusted -- only confirmed blocks count toward
    coverage()."""
    try:
        return use_case.execute(block_id, confirmed_by_sub=_user.sub)
    except AlignmentBlockNotFound as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc


@router.delete("/blocks/{block_id}", status_code=204)
def delete_alignment_block(
    block_id: int,
    use_case: DeleteAlignmentBlockUseCase = Depends(get_delete_alignment_block_use_case),
    _user: UserProfile = Depends(require_permission("alignment.edit")),
):
    try:
        use_case.execute(block_id)
    except AlignmentBlockNotFound as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc


@router.get("/coverage", response_model=AlignmentCoverageSummary)
def get_alignment_coverage(
    year: int = Query(...),
    use_case: GetAlignmentCoverageUseCase = Depends(get_get_alignment_coverage_use_case),
    _user: UserProfile = Depends(require_permission("alignment.view")),
):
    """Confirmed-only coverage so far for a year -- the progress indicator."""
    return use_case.execute(year=year)
