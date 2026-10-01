from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.domains.detection.application.use_cases import (
    ExportCampaignReportUseCase,
    GetProcessedSectorDetailUseCase,
    ListProcessedSectorsUseCase,
    ResumeSectorValidationUseCase,
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
)
from app.domains.detection.presentation.schemas.sector_history_schema import (
    ProcessedSectorDetail,
    ProcessedSectorMapItem,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Detección de construcciones — historial"])


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


def _campaign_label(campaign_id: Optional[int], campaign_repository: CampaignRepositoryPort) -> str:
    if not campaign_id:
        return "Sin campaña"
    campaign = next((c for c in campaign_repository.list_active() if c.id == campaign_id), None)
    return f"Campaña {campaign.code} · {campaign.name}" if campaign else f"Campaña #{campaign_id}"


@router.get("/sectors/export/data")
def export_campaign_report_data(
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    use_case: ExportCampaignReportUseCase = Depends(get_export_campaign_report_use_case),
    campaign_repository: CampaignRepositoryPort = Depends(get_campaign_repository),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Backs the "Exportar" preview modal and the JSON/Imprimir options --
    same confirmed/rejected rows as the Excel/PDF exports, as JSON instead of
    a file, so the frontend can render the preview table itself."""
    rows = use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only)
    return {
        "campaign_label": _campaign_label(campaign_id, campaign_repository),
        "rows": [row_to_dict(row, i) for i, row in enumerate(rows, start=1)],
    }


@router.get("/sectors/export/excel")
def export_campaign_report(
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    use_case: ExportCampaignReportUseCase = Depends(get_export_campaign_report_use_case),
    campaign_repository: CampaignRepositoryPort = Depends(get_campaign_repository),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """"Exportar" on the detection map: confirmed/rejected parcels of the
    CURRENTLY SELECTED campaign only (or unassigned sectors when none is
    selected) -- see list_report_rows for why this never spans campaigns."""
    rows = use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only)
    campaign_label = _campaign_label(campaign_id, campaign_repository)

    content = build_campaign_report_excel(rows, campaign_label)
    filename = f"reporte-predios-{campaign_id or 'sin-campania'}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sectors/export/pdf")
def export_campaign_report_pdf(
    campaign_id: Optional[int] = Query(None),
    unassigned_only: bool = Query(False),
    use_case: ExportCampaignReportUseCase = Depends(get_export_campaign_report_use_case),
    campaign_repository: CampaignRepositoryPort = Depends(get_campaign_repository),
    _user: UserProfile = Depends(require_permission("detection.view")),
):
    """Formal/presentation profile of the same export -- same rows and row
    coloring as the Excel, laid out for reading rather than editing."""
    rows = use_case.execute(campaign_id=campaign_id, unassigned_only=unassigned_only)
    campaign_label = _campaign_label(campaign_id, campaign_repository)

    content = build_campaign_report_pdf(rows, campaign_label)
    filename = f"reporte-predios-{campaign_id or 'sin-campania'}.pdf"
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
