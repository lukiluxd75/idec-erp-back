from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.domains.detection.application.use_cases import (
    ExportCampaignReportUseCase,
    GetProcessedSectorDetailUseCase,
    ListProcessedSectorsUseCase,
    ResumeSectorValidationUseCase,
    SearchDetectionEntitiesUseCase,
)
from app.domains.detection.domain.ports.campaign_repository_port import CampaignRepositoryPort
from app.domains.detection.infrastructure.export_excel import build_campaign_report_excel
from app.domains.detection.infrastructure.export_labels import row_to_dict
from app.domains.detection.infrastructure.export_pdf import build_campaign_report_pdf
from app.domains.detection.presentation.deps import (
    get_campaign_repository,
    get_export_campaign_report_use_case,
    get_list_processed_sectors_use_case,
    get_processed_sector_detail_use_case,
    get_resume_sector_validation_use_case,
    get_search_detection_entities_use_case,
)
from app.domains.detection.presentation.schemas.sector_history_schema import (
    ProcessedSectorDetail,
    ProcessedSectorMapItem,
    SearchResultItem,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Detección de construcciones — historial"])


class ChartImagePayload(BaseModel):
    title: str
    image_base64: str


class ExportPdfChartsPayload(BaseModel):
    charts: List[ChartImagePayload] = []


@router.get("/sectors", response_model=List[ProcessedSectorMapItem])
def list_processed_sectors(
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    use_case: ListProcessedSectorsUseCase = Depends(get_list_processed_sectors_use_case),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Every processed sector's polygon + summary, for the map overlay in
    "Mapa y detección" and "Historial". `unassigned_only` (ignored if
    `campaign_id` is set) backs "Mapa y detección"'s "Sin campaña" filter --
    sectors with no campaign at all, not "no filter"."""
    return use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only)


# Registered before /sectors/{processed_sector_id}: that route's int-typed
# path param would otherwise swallow this literal path and 422 on "search"
# not being a valid id (Starlette matches routes in registration order).
@router.get("/sectors/search", response_model=List[SearchResultItem])
def search_detection_entities(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=20),
    use_case: SearchDetectionEntitiesUseCase = Depends(get_search_detection_entities_use_case),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Backs the map's search box (sector id/name, predio por código
    catastral, campaña por código/nombre) and Historial's lookup -- same
    endpoint, same result shape, see SearchResult's docstring."""
    return use_case.execute(query=q, limit=limit)


def _campaign_label(
    campaign_id: Optional[int], campaign_repository: CampaignRepositoryPort, all_campaigns: bool = False
) -> str:
    if all_campaigns:
        return "Todas las campañas"
    if not campaign_id:
        return "Sin campaña"
    campaign = next((c for c in campaign_repository.list_active() if c.id == campaign_id), None)
    return f"Campaña {campaign.code} · {campaign.name}" if campaign else f"Campaña #{campaign_id}"


@router.get("/sectors/export/data")
def export_campaign_report_data(
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    all_campaigns: bool = Query(False),
    use_case: ExportCampaignReportUseCase = Depends(get_export_campaign_report_use_case),
    campaign_repository: CampaignRepositoryPort = Depends(get_campaign_repository),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Backs the "Exportar" preview modal and the JSON/Imprimir options --
    same confirmed/rejected rows as the Excel/PDF exports, as JSON instead of
    a file, so the frontend can render the preview table itself. The modal's
    own campaign selector (defaulting to whatever is active on the map) can
    override campaign_id/unassigned_only here, or set all_campaigns=True."""
    rows = use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only, all_campaigns=all_campaigns)
    return {
        "campaign_label": _campaign_label(campaign_id, campaign_repository, all_campaigns),
        "rows": [row_to_dict(row, i) for i, row in enumerate(rows, start=1)],
    }


@router.get("/sectors/export/excel")
def export_campaign_report(
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    all_campaigns: bool = Query(False),
    use_case: ExportCampaignReportUseCase = Depends(get_export_campaign_report_use_case),
    campaign_repository: CampaignRepositoryPort = Depends(get_campaign_repository),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """"Exportar" on the detection map: confirmed/rejected parcels, scoped by
    default to the campaign active on the map, but the export modal's own
    selector can pick a different one -- or all_campaigns=True for every
    campaign at once (each row keeps its own campaign_code, so this stays an
    audit listing rather than a cross-campaign rollup -- see
    list_report_rows)."""
    rows = use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only, all_campaigns=all_campaigns)
    campaign_label = _campaign_label(campaign_id, campaign_repository, all_campaigns)

    content = build_campaign_report_excel(rows, campaign_label)
    filename = f"reporte-predios-{'todas-las-campanas' if all_campaigns else (campaign_id or 'sin-campania')}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sectors/export/pdf")
def export_campaign_report_pdf(
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    all_campaigns: bool = Query(False),
    use_case: ExportCampaignReportUseCase = Depends(get_export_campaign_report_use_case),
    campaign_repository: CampaignRepositoryPort = Depends(get_campaign_repository),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Formal/presentation profile of the same export -- same rows and row
    coloring as the Excel, laid out for reading rather than editing."""
    rows = use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only, all_campaigns=all_campaigns)
    campaign_label = _campaign_label(campaign_id, campaign_repository, all_campaigns)

    content = build_campaign_report_pdf(rows, campaign_label)
    filename = f"reporte-predios-{'todas-las-campanas' if all_campaigns else (campaign_id or 'sin-campania')}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/sectors/export/pdf")
def export_campaign_report_pdf_with_charts(
    payload: ExportPdfChartsPayload,
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    all_campaigns: bool = Query(False),
    use_case: ExportCampaignReportUseCase = Depends(get_export_campaign_report_use_case),
    campaign_repository: CampaignRepositoryPort = Depends(get_campaign_repository),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Same PDF as the GET version above, plus one page per chart image --
    "Reportes" captures its own live charts as PNGs (html2canvas) and posts
    them here since a GET query string can't carry that much data. Excel and
    JSON exports never get charts (a spreadsheet/data response has nowhere
    sensible to put an image), only PDF and Imprimir."""
    rows = use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only, all_campaigns=all_campaigns)
    campaign_label = _campaign_label(campaign_id, campaign_repository, all_campaigns)

    content = build_campaign_report_pdf(
        rows, campaign_label, charts=[c.model_dump() for c in payload.charts]
    )
    filename = f"reporte-predios-{'todas-las-campanas' if all_campaigns else (campaign_id or 'sin-campania')}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sectors/{processed_sector_id}", response_model=ProcessedSectorDetail)
def get_processed_sector_detail(
    processed_sector_id: int,
    use_case: GetProcessedSectorDetailUseCase = Depends(get_processed_sector_detail_use_case),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Full history for one sector -- every run, finding, architect decision
    and feedback. Backs the map popup and Historial's detail view."""
    detail = use_case.execute(processed_sector_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Sector no encontrado.")
    return detail


@router.get("/sectors/{processed_sector_id}/resume-validation")
def resume_sector_validation(
    processed_sector_id: int,
    use_case: ResumeSectorValidationUseCase = Depends(get_resume_sector_validation_use_case),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Backs "Continuar validación": the sector's persisted `reporte.json`
    (its most recent run's full engine result, with affected_parcel_id/
    validation_status attached same as job_result) -- so the frontend can
    load it straight into the same Hallazgos table/photos a live job uses,
    no separate view needed. No response_model, same as job_result: it's the
    engine's own result shape, passed through."""
    result = use_case.execute(processed_sector_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail="No hay un resultado guardado para reanudar en este sector."
        )
    return result
