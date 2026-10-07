"""Shared human-readable labels for the campaign parcels report -- used by
the Excel, PDF and JSON/preview export paths alike (see export_excel.py,
export_pdf.py, sectors.py's export_campaign_report_data)."""
from datetime import datetime
from typing import Any, Optional

from app.domains.detection.domain.entities.affected_parcel_report_row import AffectedParcelReportRow

CHANGE_TYPE_LABEL = {
    "new": "Nueva",
    "removed": "Eliminada",
    "modified": "Cambio",
    "unchanged": "Sin cambio",
}

CONSTRUCTION_TYPE_LABEL = {
    "nueva_construccion": "Construcción nueva",
    "ampliacion": "Ampliación",
    "cambio_techo": "Cambio de techo",
    "muro_nuevo": "Muro nuevo",
    "demolicion": "Demolición",
}

VALIDATION_STATUS_LABEL = {
    "confirmed": "Confirmado",
    "rejected": "Rechazado",
}


def change_detail_label(row: AffectedParcelReportRow) -> str:
    """construction_type can be set on a confirmed finding of ANY change_type
    (new/removed/modified), not just "modified" ones -- verified against real
    data (e.g. a "removed" finding classified with the architect's own
    free-text label)."""
    return CONSTRUCTION_TYPE_LABEL.get(row.construction_type, row.construction_type or "")


def fmt_datetime(value: Optional[datetime]) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else ""


def row_to_dict(row: AffectedParcelReportRow, index: int) -> dict[str, Any]:
    """One row shaped for the export preview/JSON download -- same fields and
    labels as the Excel/PDF exports, English keys (see CLAUDE.md §1: new code
    is English, snake_case)."""
    return {
        "number": index,
        "sector_name": row.sector_name or f"Sector #{row.sector_id}",
        "cadastral_code": row.cadastral_code or "",
        "change_type": row.change_type,
        "change_type_label": CHANGE_TYPE_LABEL.get(row.change_type, row.change_type),
        "change_detail": change_detail_label(row),
        "validation_status": row.validation_status,
        "validation_status_label": VALIDATION_STATUS_LABEL.get(row.validation_status, row.validation_status),
        "rejection_comment": row.rejection_comment or "",
        "years": f"{row.year_a} → {row.year_b}",
        "campaign_code": row.campaign_code or "",
        "probability_pct": row.probability_pct,
        "validated_by_username": row.validated_by_username or "",
        "validated_at": fmt_datetime(row.validated_at),
        "lon": row.lon,
        "lat": row.lat,
    }
